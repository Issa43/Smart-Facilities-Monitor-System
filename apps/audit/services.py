from .models import AuditLog


def record_audit(*, actor, action, entity, before=None, after=None, request=None):
    meta = getattr(request, "META", {}) if request is not None else {}
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded.split(",")[0].strip() if forwarded else meta.get("REMOTE_ADDR")
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity._meta.label_lower,
        entity_id=str(entity.pk),
        entity_ref=str(entity)[:255],
        before=before,
        after=after,
        ip_address=ip_address or None,
        user_agent=meta.get("HTTP_USER_AGENT", "")[:500],
    )
