This application owns durable, recipient-specific Notification and
NotificationPreference models, private DeviceRegistration records,
per-device PushDelivery state, persistence services, scheduled Celery tasks,
migrations, and tests. Its REST API serializers, views, and routes live under
`api/v1/platform/`.

Eligible camera SecurityAlerts persist Notification rows in the originating
transaction, then enqueue FCM delivery after commit. Firebase initialization is
lazy and credentials come only from mounted runtime configuration. Tokens are
write-only at the API boundary and must never be logged.

It does not own the live security WebSocket. That independent best-effort path
is implemented by `apps/security/consumers.py`, `routing.py`, and `realtime.py`.
