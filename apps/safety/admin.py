"""Django Admin provisioning for Telegram safety destinations.

This is the only way a chat id enters the system: there is no REST endpoint,
no self-service flow, and no import command. Delivery rows are shown read-only
so an operator can audit what was sent without being able to forge a send.
"""

from django.contrib import admin

from .models import (
    ProjectTelegramDestination,
    SafetyActionProposal,
    SafetyTelegramDelivery,
    SafetyTelegramRecipient,
)


@admin.register(SafetyTelegramRecipient)
class SafetyTelegramRecipientAdmin(admin.ModelAdmin):
    list_display = ("user", "chat_id", "is_enabled", "is_active", "updated_at")
    list_filter = ("is_enabled", "is_active")
    search_fields = ("user__email", "user__full_name", "chat_id")
    autocomplete_fields = ("user",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("user", "chat_id", "is_enabled", "is_active")}),
        ("Record", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        # full_clean runs the chat-id format and phone-number checks even when
        # a field is set outside the form.
        if obj.created_by_id is None:
            obj.created_by = request.user
        obj.full_clean(validate_unique=False)
        super().save_model(request, obj, form, change)


@admin.register(SafetyTelegramDelivery)
class SafetyTelegramDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "alert",
        "recipient",
        "status",
        "attempt_count",
        "failure_code",
        "sent_at",
    )
    list_filter = ("status",)
    search_fields = ("event_key", "failure_code", "provider_message_id")
    ordering = ("-created_at",)
    list_select_related = ("alert", "recipient")
    readonly_fields = tuple(
        field.name for field in SafetyTelegramDelivery._meta.fields
    )

    def has_add_permission(self, request):
        # Deliveries exist only as the result of a recorded human decision.
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SafetyActionProposal)
class SafetyActionProposalAdmin(admin.ModelAdmin):
    """Read-only window onto the human decision workflow.

    Proposals and rulings are made by the responsible managers through the
    API, where scope, separation of duties and audit are enforced. Admin can
    read them but never create or alter one, so no decision can be forged here.
    """

    list_display = (
        "alert",
        "decision_type",
        "proposed_action",
        "status",
        "proposed_by",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("decision_type", "status")
    search_fields = ("proposal_notes", "review_notes")
    ordering = ("-proposed_at",)
    list_select_related = ("alert", "proposed_by", "reviewed_by")
    readonly_fields = tuple(field.name for field in SafetyActionProposal._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProjectTelegramDestination)
class ProjectTelegramDestinationAdmin(admin.ModelAdmin):
    """Where each project's approved worker instructions are delivered.

    This is the only way a project chat id enters the system: there is no REST
    endpoint, no self-service flow and no import command, so a chat id can
    never be set from the frontend or from a hazard payload.
    """

    list_display = ("project", "display_name", "chat_id", "is_enabled", "is_active", "updated_at")
    list_filter = ("is_enabled", "is_active")
    search_fields = ("project__name", "display_name", "chat_id")
    # Projects have no Admin of their own, so a plain select is used here
    # rather than an autocomplete that would have nothing to query.
    raw_id_fields = ("project",)
    ordering = ("project__name",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("project", "chat_id", "display_name", "is_enabled", "is_active")}),
        ("Record", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        if obj.created_by_id is None:
            obj.created_by = request.user
        obj.full_clean(validate_unique=False)
        super().save_model(request, obj, form, change)
