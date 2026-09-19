"""Explicit, validated filters for the Safety API.

Filters only narrow an already-scoped queryset; none can widen access.
"""

import django_filters

from apps.safety.models import HazardEvent, ProjectSafetyAlert, SafetyActionProposal

from .permissions import scoped_projects


class DateRangeFilterSet(django_filters.FilterSet):
    date_range_pairs = ()

    def is_valid(self):
        valid = super().is_valid()
        if not valid:
            return False
        for start_name, end_name in self.date_range_pairs:
            start = self.form.cleaned_data.get(start_name)
            end = self.form.cleaned_data.get(end_name)
            if start and end and start > end:
                self.form.add_error(end_name, f"{end_name} must not be earlier than {start_name}.")
                valid = False
        return valid


class ProjectSafetyAlertFilter(DateRangeFilterSet):
    date_range_pairs = (("created_after", "created_before"),)

    project = django_filters.UUIDFilter(field_name="project_id")
    severity = django_filters.ChoiceFilter(choices=ProjectSafetyAlert.Severity.choices)
    status = django_filters.ChoiceFilter(choices=ProjectSafetyAlert.Status.choices)
    hazard_type = django_filters.ChoiceFilter(choices=HazardEvent.HazardType.choices)
    provider = django_filters.ChoiceFilter(
        field_name="hazard_event__provider",
        choices=HazardEvent.Provider.choices,
    )
    hazard_withdrawn = django_filters.BooleanFilter(method="filter_hazard_withdrawn")
    created_after = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = ProjectSafetyAlert
        fields = []

    def filter_hazard_withdrawn(self, queryset, name, value):
        return queryset.filter(hazard_withdrawn_at__isnull=not value)


class HazardEventFilter(DateRangeFilterSet):
    date_range_pairs = (("occurred_after", "occurred_before"),)

    provider = django_filters.ChoiceFilter(choices=HazardEvent.Provider.choices)
    hazard_type = django_filters.ChoiceFilter(choices=HazardEvent.HazardType.choices)
    alert_level = django_filters.ChoiceFilter(choices=HazardEvent.AlertLevel.choices)
    provider_status = django_filters.ChoiceFilter(choices=HazardEvent.ProviderStatus.choices)
    project = django_filters.UUIDFilter(method="filter_project")
    occurred_after = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="gte")
    occurred_before = django_filters.IsoDateTimeFilter(field_name="occurred_at", lookup_expr="lte")

    class Meta:
        model = HazardEvent
        fields = []

    def filter_project(self, queryset, name, value):
        # Only projects inside the caller's scope may be used, so the filter
        # can never reveal which out-of-scope projects an event affected.
        user = getattr(self.request, "user", None)
        if not scoped_projects(user).filter(pk=value).exists():
            return queryset.none()
        return queryset.filter(project_alerts__project_id=value).distinct()


class SafetyActionProposalFilter(django_filters.FilterSet):
    """Narrow the proposal list without widening what it can reach.

    Every filter runs on top of the already-scoped queryset, so a manager
    filtering by project cannot see proposals on a project outside their own
    assignments.
    """

    decision_type = django_filters.ChoiceFilter(
        choices=SafetyActionProposal.DecisionType.choices
    )
    status = django_filters.ChoiceFilter(choices=SafetyActionProposal.Status.choices)
    alert = django_filters.UUIDFilter(field_name="alert_id")
    project = django_filters.UUIDFilter(field_name="alert__project_id")
    mine = django_filters.BooleanFilter(method="filter_mine")

    class Meta:
        model = SafetyActionProposal
        fields = []

    def filter_mine(self, queryset, name, value):
        user = getattr(self.request, "user", None)
        if not getattr(user, "pk", None):
            return queryset.none()
        return queryset.filter(proposed_by=user) if value else queryset.exclude(proposed_by=user)
