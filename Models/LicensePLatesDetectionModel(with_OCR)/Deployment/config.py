from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# ============================================================
# PATHS
# ============================================================

# Custom-trained plate detector weights. Not committed to git —
# place your own best.pt next to this file before running.
MODEL_PATH = PROJECT_DIR / "best.pt"

# COCO-pretrained vehicle classifier. Ultralytics will download it
# automatically if it isn't found locally.
VEHICLE_MODEL_PATH = "yolo26n.pt"

# Not committed to git — point this at a local test video, e.g.
# VIDEO_PATH = PROJECT_DIR / "sample_video.mp4"
VIDEO_PATH = PROJECT_DIR / "VID_sample.mp4"
OUTPUT_PATH = PROJECT_DIR / "output_fast.mp4"


# ============================================================
# SETTINGS
# ============================================================

USE_GPU = True
DETECT_EVERY = 2
OCR_EVERY = 2
YOLO_IMGSZ = 960
YOLO_CONF = 0.20
HISTORY_SIZE = 20
MIN_VOTES = 3
TRACK_TIMEOUT_FRAMES = 30

SAVE_DEBUG = True
MAX_DEBUG_IMAGES = 60
DEBUG_FOLDER = str(PROJECT_DIR / "debug_plates")

# ============================================================
# VEHICLE TYPE CLASSIFICATION SETTINGS
# ============================================================

VEHICLE_DETECT_EVERY = 4  # vehicle type changes slowly, so run this less often than plate tracking
VEHICLE_CONF = 0.35

COCO_VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck"
}


# ============================================================
# DIRECTION LINE SETTINGS
# ============================================================

LINE_P1_RATIO = (0.0, 0.55)
LINE_P2_RATIO = (1.0, 0.55)

SIDE_POSITIVE_LABEL = "IN"
SIDE_NEGATIVE_LABEL = "OUT"

CROSSING_CONFIRM_FRAMES = 3
