from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.settings import api_settings

from apps.assets.models import Asset
from apps.projects.models import Project
from apps.safety.models import (
    SYSTEM_RECOMMENDABLE_ACTION_VALUES,
    HazardEvent,
    ProjectSafetyAlert,
    SafetyActionProposal,
)
from apps.safety.recipients import user_can_approve_safety, user_can_propose
from apps.safety.proposals import MAX_SCOPE_LENGTH
from apps.safety.services import MAX_NOTES_LENGTH, available_actions
from apps.users.models import User


RECOMMENDED_ACTION_CHOICES = [
    choice for choice in ProjectSafetyAlert.Action.choices if choice[0] in SYSTEM_RECOMMENDABLE_ACTION_VALUES
]
# Same values as other low/medium/high/critical sets, but a distinct, explicitly
# labelled OpenAPI choice set so existing enum component names stay unchanged.
SAFETY_SEVERITY_CHOICES = [
    (value, f"{label} safety alert severity") for value, label in ProjectSafetyAlert.Severity.choices
]
# A finished alert takes no new proposals.
CLOSED_ALERT_STATUSES = frozenset(
    {ProjectSafetyAlert.Status.CLOSED, ProjectSafetyAlert.Status.DISMISSED}
)


class StrictInputSerializer(serializers.Serializer):
    """Reject fields outside the explicit request contract."""

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            # A dict keeps DRF's error structure valid (a bare string would
            # turn a malformed request into a 500).
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: ["Expected an object payload."]}
            )
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {field: "This field is not allowed." for field in unknown}
            )
        return super().to_internal_value(data)


class SafetyUserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "full_name"]
        read_only_fields = fields


class SafetyProjectSummarySerializer(serializers.ModelSerializer):
    facility_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Project
        fields = ["id", "name", "location", "status", "facility_id"]
        read_only_fields = fields


class HazardEventReadSerializer(serializers.ModelSerializer):
    """Normalized provider facts. The raw provider payload is never exposed."""

    class Meta:
        model = HazardEvent
        fields = [
            "id",
            "provider",
            "provider_event_id",
            "hazard_type",
            "title",
            "alert_level",
            "provider_severity",
            "magnitude",
            "depth_km",
            "latitude",
            "longitude",
            "radius_km",
            "occurred_at",
            "valid_from",
            "valid_until",
            "provider_updated_at",
            "provider_status",
            "revision",
            "source_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SafetyActionProposalSummarySerializer(serializers.ModelSerializer):
    """An open proposal as shown inline on its alert.

    Deliberately excludes the alert itself, which would recurse.
    """

    proposed_by = SafetyUserSummarySerializer(read_only=True)
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = SafetyActionProposal
        fields = [
            "id",
            "decision_type",
            "proposed_action",
            "proposal_notes",
            "effective_from",
            "effective_until",
            "worker_scope",
            "status",
            "proposed_by",
            "proposed_at",
            "can_review",
        ]
        read_only_fields = fields

    def get_can_review(self, obj) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(
            obj.status == SafetyActionProposal.Status.PENDING_MANAGER_REVIEW
            and user_can_approve_safety(user)
            and getattr(user, "pk", None) != obj.proposed_by_id
        )


class ProjectSafetyAlertReadSerializer(serializers.ModelSerializer):
    project = SafetyProjectSummarySerializer(read_only=True)
    hazard_event = HazardEventReadSerializer(read_only=True)
    acknowledged_by = SafetyUserSummarySerializer(read_only=True, allow_null=True)
    decided_by = SafetyUserSummarySerializer(read_only=True, allow_null=True)
    resolved_by = SafetyUserSummarySerializer(read_only=True, allow_null=True)
    severity = serializers.ChoiceField(choices=SAFETY_SEVERITY_CHOICES, read_only=True)
    # The model restricts recommendations to system actions ("other" is human-only).
    recommended_action = serializers.ChoiceField(choices=RECOMMENDED_ACTION_CHOICES, read_only=True)
    available_actions = serializers.SerializerMethodField()
    available_proposal_types = serializers.SerializerMethodField()
    open_proposals = serializers.SerializerMethodField()

    class Meta:
        model = ProjectSafetyAlert
        fields = [
            "id",
            "project",
            "hazard_event",
            "hazard_type",
            "severity",
            "status",
            "distance_km",
            "project_latitude",
            "project_longitude",
            "rule_code",
            "policy_version",
            "recommended_action",
            "decision",
            "decision_notes",
            "acknowledged_by",
            "acknowledged_at",
            "decided_by",
            "decided_at",
            "resolution_notes",
            "resolved_by",
            "resolved_at",
            "hazard_withdrawn_at",
            "escalated_at",
            "available_actions",
            "available_proposal_types",
            "open_proposals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_available_actions(self, obj) -> list[str]:
        # Scope is already enforced by the view queryset; the workflow state
        # machine in apps.safety.services decides which actions apply.
        if not self.context.get("can_manage"):
            return []
        return available_actions(obj)

    @extend_schema_field(
        serializers.ListField(child=serializers.CharField(), allow_empty=True)
    )
    def get_available_proposal_types(self, obj) -> list[str]:
        """Which protective actions *this* viewer may propose on this alert.

        Server-calculated for the same reason as ``available_actions``: the
        client must never decide what a role is allowed to do. It reflects the
        caller's own permissions and assignment scope, so a Construction
        Manager sees only worker protection and an Operations Manager only
        asset protection.
        """

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or obj.status in CLOSED_ALERT_STATUSES:
            return []
        open_types = set(
            obj.action_proposals.filter(
                status=SafetyActionProposal.Status.PENDING_MANAGER_REVIEW
            ).values_list("decision_type", flat=True)
        )
        return [
            decision_type
            for decision_type in SafetyActionProposal.DecisionType.values
            # An open ask of this kind is already with the approver.
            if decision_type not in open_types
            and user_can_propose(user, obj, decision_type)
        ]

    @extend_schema_field(SafetyActionProposalSummarySerializer(many=True))
    def get_open_proposals(self, obj):
        """Proposals still awaiting a ruling, newest first."""

        proposals = obj.action_proposals.filter(
            status=SafetyActionProposal.Status.PENDING_MANAGER_REVIEW
        ).select_related("proposed_by").order_by("-proposed_at")
        return SafetyActionProposalSummarySerializer(
            proposals, many=True, context=self.context
        ).data


class AlertAcknowledgeInputSerializer(StrictInputSerializer):
    pass


class AlertDecisionInputSerializer(StrictInputSerializer):
    decision = serializers.ChoiceField(choices=ProjectSafetyAlert.Action.choices)
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_NOTES_LENGTH,
    )


class AlertDismissInputSerializer(StrictInputSerializer):
    reason = serializers.CharField(allow_blank=False, max_length=MAX_NOTES_LENGTH)


class AlertCloseInputSerializer(StrictInputSerializer):
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_NOTES_LENGTH,
    )


class SafetyAssetSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["id", "name", "asset_type", "current_status"]
        read_only_fields = fields


class SafetyActionProposalReadSerializer(serializers.ModelSerializer):
    alert = ProjectSafetyAlertReadSerializer(read_only=True)
    proposed_by = SafetyUserSummarySerializer(read_only=True)
    reviewed_by = SafetyUserSummarySerializer(read_only=True, allow_null=True)
    affected_assets = SafetyAssetSummarySerializer(many=True, read_only=True)
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = SafetyActionProposal
        fields = [
            "id",
            "alert",
            "decision_type",
            "proposed_action",
            "proposal_notes",
            "effective_from",
            "effective_until",
            "worker_scope",
            "status",
            "affected_assets",
            "proposed_by",
            "proposed_at",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
            "can_review",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_can_review(self, obj) -> bool:
        """Whether *this* viewer may rule on *this* proposal.

        Server-calculated so the client never infers authority from a role
        name. It mirrors the service rule exactly, including the separation of
        duties that stops anyone ruling on their own ask.
        """

        user = self.context.get("request").user if self.context.get("request") else None
        return bool(
            obj.status == SafetyActionProposal.Status.PENDING_MANAGER_REVIEW
            and user_can_approve_safety(user)
            and getattr(user, "pk", None) != obj.proposed_by_id
        )


class ProposalCreateInputSerializer(StrictInputSerializer):
    decision_type = serializers.ChoiceField(choices=SafetyActionProposal.DecisionType.choices)
    proposed_action = serializers.ChoiceField(choices=ProjectSafetyAlert.Action.choices)
    notes = serializers.CharField(allow_blank=False, max_length=MAX_NOTES_LENGTH)
    asset_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        max_length=50,
    )
    effective_from = serializers.DateTimeField(required=False, allow_null=True, default=None)
    effective_until = serializers.DateTimeField(required=False, allow_null=True, default=None)
    worker_scope = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_SCOPE_LENGTH,
    )

    def validate(self, attrs):
        start, end = attrs.get("effective_from"), attrs.get("effective_until")
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"effective_until": "The end of the window must be after its start."}
            )
        return attrs


class ProposalApproveInputSerializer(StrictInputSerializer):
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=MAX_NOTES_LENGTH,
    )


class ProposalRejectInputSerializer(StrictInputSerializer):
    reason = serializers.CharField(allow_blank=False, max_length=MAX_NOTES_LENGTH)


class SafetyMonitoringCoverageSerializer(serializers.Serializer):
    monitored_projects = serializers.IntegerField()
    projects_with_coordinates = serializers.IntegerField()
    projects_missing_coordinates = serializers.IntegerField()
    alert_creation_enabled = serializers.BooleanField()
