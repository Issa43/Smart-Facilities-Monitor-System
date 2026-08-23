from django.db import transaction

from apps.common.models import SystemSetting

from .models import Notification, NotificationPreference


def setting_enabled(key, *, default=True):
    value = SystemSetting.objects.filter(key=key).values_list("value", flat=True).first()
    return value if isinstance(value, bool) else default


def notify_users(
    users,
    *,
    title,
    body,
    category,
    tone=Notification.Tone.INFO,
    href=None,
    source=None,
    preference_field=None,
    system_setting_key=None,
):
    if system_setting_key and not setting_enabled(system_setting_key):
        return
    recipient_ids = {
        user.pk for user in users if user and getattr(user, "pk", None) and user.is_active
    }
    if preference_field and recipient_ids:
        disabled_ids = NotificationPreference.objects.filter(
            user_id__in=recipient_ids,
            **{preference_field: False},
        ).values_list("user_id", flat=True)
        recipient_ids.difference_update(disabled_ids)
    if not recipient_ids:
        return
    source_type = source._meta.label_lower if source is not None else None
    source_id = source.pk if source is not None else None

    def persist():
        Notification.objects.bulk_create(
            [
                Notification(
                    recipient_id=recipient_id,
                    title=title,
                    body=body,
                    category=category,
                    tone=tone,
                    href=href,
                    source_type=source_type,
                    source_id=source_id,
                )
                for recipient_id in recipient_ids
            ]
        )

    transaction.on_commit(persist)


def notify_user(user, **kwargs):
    notify_users([user], **kwargs)
