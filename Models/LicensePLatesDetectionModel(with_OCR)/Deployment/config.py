# ============================================================
# PATHS
# ============================================================

# Where files live is kept in paths.py, the only file that differs between the
# local test copy and the deployment copy. Everything in this file is shared.
from paths import (  # noqa: F401
    DEBUG_FOLDER,
    INPUT_PATH,
    MODEL_PATH,
    OUTPUT_DIR,
    OUTPUT_PATH,
    PROJECT_DIR,
    VEHICLE_MODEL_PATH,
)

VIDEO_PATH = INPUT_PATH  # backward-compatible alias

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".mpg", ".mpeg", ".webm"}


# ============================================================
# SETTINGS
# ============================================================

# "paddle" (ocr_paddle.py) or "easyocr" (ocr.py). On the 83 TestingOCR photos
# paddle read 80 correct / 0 wrong, easyocr 33 correct / 39 wrong.
OCR_ENGINE = "paddle"
# small: ~70 ms median per plate on CPU. PP-OCRv6_medium_rec reads tiny crops
# slightly better but takes ~0.7 s per plate.
PADDLE_REC_MODEL = "PP-OCRv6_small_rec"

# EasyOCR GPU initialization hangs in this deployment environment; YOLO still
# loads and runs independently of this OCR setting.
USE_GPU = True
DETECT_EVERY = 2
OCR_EVERY = 2
YOLO_IMGSZ = 1024
YOLO_CONF = 0.20
HISTORY_SIZE = 20
MIN_VOTES = 3
# Once this many reads agree, the plate is settled and the track is no longer
# OCR'd: more reads of a known plate only cost time.
LOCK_VOTES = 5
TRACK_TIMEOUT_FRAMES = 30

SHOW_WINDOW = True
# The preview is scaled down to fit this share of the screen, so a portrait
# 1080x1920 video is shown whole. Output files keep their full resolution.
WINDOW_SCREEN_FRACTION = 0.95
IMAGE_DISPLAY_MS = 0        # 0 = wait for a key press on each photo

SAVE_DEBUG = True
MAX_DEBUG_IMAGES = 60

# ============================================================
# VEHICLE TYPE CLASSIFICATION SETTINGS
# ============================================================

VEHICLE_DETECT_EVERY = 4            # vehicle type changes slowly, so run this less often than plate tracking
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