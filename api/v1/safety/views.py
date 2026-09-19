"""Safety REST API: a thin interface over the existing Safety domain.

Read endpoints use server-side scoped querysets, so out-of-scope records are
404. Workflow endpoints call the ``apps.safety.services`` workflow functions,
which own the state machine, scope re-check, and semantic audit. Hazard events
and alerts are never created or edited through this API.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from api.v1.exceptions import DomainConflict
from apps.safety.policy import alert_creation_enabled
from apps.safety.proposals import approve_proposal, create_proposal, reject_proposal
from apps.safety.recipients import SAFETY_MANAGE_PERMISSION
from apps.safety.services import (
    acknowledge_alert,
    close_alert,
    decide_alert_action,
    dismiss_alert,
    monitored_projects,
)

from .filters import HazardEventFilter, ProjectSafetyAlertFilter, SafetyActionProposalFilter
from .permissions import (
    CanUseSafetyAlerts,
    hazard_events_for_user,
    safety_alerts_for_user,
    safety_proposals_for_user,
    scoped_projects,
    user_can_manage_safety,
)
from .serializers import (
    AlertAcknowledgeInputSerializer,
    AlertCloseInputSerializer,
    AlertDecisionInputSerializer,
    AlertDismissInputSerializer,
    HazardEventReadSerializer,
    ProjectSafetyAlertReadSerializer,
    ProposalApproveInputSerializer,
    ProposalCreateInputSerializer,
    ProposalRejectInputSerializer,
    SafetyActionProposalReadSerializer,
    SafetyMonitoringCoverageSerializer,
)


UUID_REGEX = (
    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _domain_conflict(error):
    details = getattr(error, "message_dict", None) or {"non_field_errors": error.messages}
    return DomainConflict(detail=details)


class ProjectSafetyAlertViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanUseSafetyAlerts]
    permission_required = {
        "acknowledge": SAFETY_MANAGE_PERMISSION,
        "decide": SAFETY_MANAGE_PERMISSION,
        "dismiss": SAFETY_MANAGE_PERMISSION,
        "close": SAFETY_MANAGE_PERMISSION,
        "default": None,
    }
    serializer_class = ProjectSafetyAlertReadSerializer
    filterset_class = ProjectSafetyAlertFilter
    search_fields = ["project__name", "hazard_event__title"]
    ordering_fields = ["created_at", "updated_at", "distance_km"]
    ordering = ["-created_at"]
    lookup_value_regex = UUID_REGEX

    def get_queryset(self):
        return safety_alerts_for_user(self.request.user).select_related(
            "project",
            "hazard_event",
            "acknowledged_by",
            "decided_by",
            "resolved_by",
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_manage"] = user_can_manage_safety(self.request.user)
        return context

    def _workflow(self, service, **kwargs):
        alert = self.get_object()
        try:
            alert = service(alert_id=alert.pk, actor=self.request.user, request=self.request, **kwargs)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied() from exc
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return Response(self.get_serializer(alert).data)

    @extend_schema(request=AlertAcknowledgeInputSerializer, responses=ProjectSafetyAlertReadSerializer)
    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, pk=None):
        AlertAcknowledgeInputSerializer(data=request.data).is_valid(raise_exception=True)
        return self._workflow(acknowledge_alert)

    @extend_schema(request=AlertDecisionInputSerializer, responses=ProjectSafetyAlertReadSerializer)
    @action(detail=True, methods=["post"], url_path="decide")
    def decide(self, request, pk=None):
        payload = AlertDecisionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._workflow(
            decide_alert_action,
            decision=payload.validated_data["decision"],
            notes=payload.validated_data["notes"],
        )

    @extend_schema(request=AlertDismissInputSerializer, responses=ProjectSafetyAlertReadSerializer)
    @action(detail=True, methods=["post"], url_path="dismiss")
    def dismiss(self, request, pk=None):
        payload = AlertDismissInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._workflow(dismiss_alert, reason=payload.validated_data["reason"])

    @extend_schema(request=AlertCloseInputSerializer, responses=ProjectSafetyAlertReadSerializer)
    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        payload = AlertCloseInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._workflow(close_alert, notes=payload.validated_data["notes"])

    @extend_schema(
        request=ProposalCreateInputSerializer,
        responses={201: SafetyActionProposalReadSerializer},
    )
    @action(detail=True, methods=["post"], url_path="proposals")
    def propose(self, request, pk=None):
        """Propose a protective action on this alert, for approval.

        Nested under the alert so the target is the object the caller's scope
        was already checked against. Which kind of proposal the caller may
        raise is decided by permission, in the service.
        """

        payload = ProposalCreateInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        alert = self.get_object()
        try:
            proposal = create_proposal(
                alert_id=alert.pk,
                actor=request.user,
                request=request,
                decision_type=payload.validated_data["decision_type"],
                proposed_action=payload.validated_data["proposed_action"],
                notes=payload.validated_data["notes"],
                asset_ids=payload.validated_data["asset_ids"],
                effective_from=payload.validated_data["effective_from"],
                effective_until=payload.validated_data["effective_until"],
                worker_scope=payload.validated_data["worker_scope"],
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc) or None) from exc
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        serializer = SafetyActionProposalReadSerializer(
            proposal, context=self.get_serializer_context()
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SafetyActionProposalViewSet(
    mixins.CreateModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Protective actions managers propose and the General Manager rules on.

    Every authorization decision is made by ``apps.safety.proposals``; this
    layer only shapes requests and responses. Creation is nested under an alert
    so the proposal can never name a different one than the caller is scoped to.
    """

    permission_classes = [CanUseSafetyAlerts]
    serializer_class = SafetyActionProposalReadSerializer
    filterset_class = SafetyActionProposalFilter
    ordering_fields = ["proposed_at", "reviewed_at", "created_at"]
    ordering = ["-proposed_at"]
    lookup_value_regex = UUID_REGEX

    def get_queryset(self):
        return safety_proposals_for_user(self.request.user).select_related(
            "alert__project",
            "alert__hazard_event",
            "proposed_by",
            "reviewed_by",
        ).prefetch_related("affected_assets")

    def _service(self, service, **kwargs):
        try:
            proposal = service(actor=self.request.user, request=self.request, **kwargs)
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc) or None) from exc
        except DjangoValidationError as exc:
            raise _domain_conflict(exc) from exc
        return proposal

    @extend_schema(
        request=ProposalCreateInputSerializer,
        responses={201: SafetyActionProposalReadSerializer},
    )
    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST")

    @extend_schema(
        request=ProposalApproveInputSerializer,
        responses=SafetyActionProposalReadSerializer,
    )
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        payload = ProposalApproveInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        proposal = self._service(
            approve_proposal,
            proposal_id=self.get_object().pk,
            notes=payload.validated_data["notes"],
        )
        return Response(self.get_serializer(proposal).data)

    @extend_schema(
        request=ProposalRejectInputSerializer,
        responses=SafetyActionProposalReadSerializer,
    )
    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        payload = ProposalRejectInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        proposal = self._service(
            reject_proposal,
            proposal_id=self.get_object().pk,
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(proposal).data)


class HazardEventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [CanUseSafetyAlerts]
    serializer_class = HazardEventReadSerializer
    filterset_class = HazardEventFilter
    search_fields = ["title"]
    ordering_fields = ["occurred_at", "provider_updated_at", "created_at"]
    ordering = ["-occurred_at"]
    lookup_value_regex = UUID_REGEX

    def get_queryset(self):
        return hazard_events_for_user(self.request.user)


class SafetyMonitoringCoverageView(APIView):
    permission_classes = [CanUseSafetyAlerts]

    @extend_schema(responses=SafetyMonitoringCoverageSerializer)
    def get(self, request):
        projects = monitored_projects().filter(pk__in=scoped_projects(request.user).values("pk"))
        total = projects.count()
        with_coordinates = projects.filter(latitude__isnull=False, longitude__isnull=False).count()
        data = {
            "monitored_projects": total,
            "projects_with_coordinates": with_coordinates,
            "projects_missing_coordinates": total - with_coordinates,
            "alert_creation_enabled": alert_creation_enabled(),
        }
        return Response(SafetyMonitoringCoverageSerializer(data).data)
