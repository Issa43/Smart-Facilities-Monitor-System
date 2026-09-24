
import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / 'best.pt'
DEVICE = 0
VIDEO_SOURCE = 0
BACKEND_ALERT_URL = None


def _env_float(name, default):
    raw = os.environ.get(name, '').strip()
    return float(raw) if raw else default


def _env_int(name, default):
    raw = os.environ.get(name, '').strip()
    return int(raw) if raw else default


FRAME_SKIP = _env_int('FRAME_SKIP', 5)
IMAGE_SIZE = 640
WINDOW_SIZE = _env_int('WINDOW_SIZE', 6)

# 0.378 is the F1-optimal point on the test set. Raising it for a live camera
# is the wrong lever against false alarms: it drops the detections the model
# finds hard -- small, distant, dim fire -- which is the early-stage fire the
# system exists to catch. False alarms are filtered by the window below.
CONF_THRESHOLD = _env_float('CONF_THRESHOLD', 0.378)

# How many of the last WINDOW_SIZE sampled frames must be positive before an
# alert is raised. Higher = fewer false alarms, slightly slower to trigger.
# Fire needs more corroboration than Smoke: its per-frame precision is lower
# (~0.73 vs ~0.83 on the test set), and smoke usually precedes fire, so it is
# the earlier warning and should be the faster one to trip.
ALERT_THRESHOLD = {
    'Fire': _env_int('FIRE_ALERT_FRAMES', 4),
    'Smoke': _env_int('SMOKE_ALERT_FRAMES', 3),
}

# A check older than this leaves the window, so a window never mixes checks
# from before and after a stream outage. Six checks normally span ~1.7 s; the
# margin leaves room for slower CPU inference.
WINDOW_MAX_AGE_SECONDS = _env_float('WINDOW_MAX_AGE_SECONDS', 10)

# One alert per incident: after the first alert a class stays quiet, apart from
# a reminder every ALERT_REMINDER_SECONDS while the incident is still being
# confirmed. The incident closes once the class has gone undetected for
# INCIDENT_CLEAR_SECONDS; the next confirmation raises a new alert. 30 s rides
# out smoke that flickers in and out of detection: on the sample video, 10 s
# turned one smoke event into several alerts.
ALERT_REMINDER_SECONDS = _env_float('ALERT_REMINDER_SECONDS', 300)
INCIDENT_CLEAR_SECONDS = _env_float('INCIDENT_CLEAR_SECONDS', 30)
