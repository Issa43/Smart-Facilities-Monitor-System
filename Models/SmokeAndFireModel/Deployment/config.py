
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / 'best.pt'
DEVICE = 0
VIDEO_SOURCE = 0
BACKEND_ALERT_URL = None

FRAME_SKIP = 5
CONF_THRESHOLD = 0.378   # This value from test set F1_curve
IMAGE_SIZE = 640
WINDOW_SIZE = 6

ALERT_THRESHOLD = {'Fire': 3, 'Smoke': 4}
COOLDOWN_SECONDS = 15