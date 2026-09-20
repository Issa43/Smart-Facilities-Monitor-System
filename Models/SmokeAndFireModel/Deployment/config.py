
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

# 0.378 is the F1-optimal point on the test set: the best precision/recall
# balance for scoring the benchmark. A live camera is a different problem --
# it runs for hours against scenes the test set never contained (warm lamps,
# skin tones, sunlight on walls), and at 0.378 those produce a steady trickle
# of false fire/smoke alerts. Deployments raise this; the benchmark value
# stays the default so evaluation results remain reproducible.
CONF_THRESHOLD = _env_float('CONF_THRESHOLD', 0.378)

# How many of the last WINDOW_SIZE sampled frames must be positive before an
# alert is raised. Higher = fewer false alarms, slightly slower to trigger.
ALERT_THRESHOLD = {
    'Fire': _env_int('FIRE_ALERT_FRAMES', 3),
    'Smoke': _env_int('SMOKE_ALERT_FRAMES', 4),
}
COOLDOWN_SECONDS = _env_int('COOLDOWN_SECONDS', 15)
