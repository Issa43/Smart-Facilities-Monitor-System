import threading
from pathlib import Path

from django.conf import settings


FIREBASE_APP_NAME = "sflms-fcm"
_initialization_lock = threading.Lock()


class FCMUnavailable(RuntimeError):
    """FCM is disabled or its server credentials are unavailable."""


def configuration_status():
    enabled = bool(settings.FCM_ENABLED)
    credentials_path = str(settings.FCM_CREDENTIALS_PATH or "").strip()
    project_id = str(settings.FCM_PROJECT_ID or "").strip()
    return {
        "enabled": enabled,
        "configured": bool(enabled and credentials_path and project_id),
    }


def get_firebase_app():
    status = configuration_status()
    if not status["configured"]:
        raise FCMUnavailable("FCM is not configured.")

    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app(FIREBASE_APP_NAME)
    except ValueError:
        pass

    with _initialization_lock:
        try:
            return firebase_admin.get_app(FIREBASE_APP_NAME)
        except ValueError:
            credentials_path = Path(settings.FCM_CREDENTIALS_PATH)
            if not credentials_path.is_file():
                raise FCMUnavailable("FCM credentials are unavailable.")
            try:
                credential = credentials.Certificate(str(credentials_path))
                return firebase_admin.initialize_app(
                    credential,
                    {"projectId": settings.FCM_PROJECT_ID},
                    name=FIREBASE_APP_NAME,
                )
            except (OSError, ValueError) as exc:
                raise FCMUnavailable("FCM credentials are unavailable.") from exc


def send_push(*, token, title, body, data):
    from firebase_admin import messaging

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={key: str(value) for key, value in data.items()},
        token=token,
    )
    return messaging.send(message, app=get_firebase_app())
