"""
Plate reading with PaddleOCR's text-line recognizer.

Drop-in alternative to the EasyOCR engine in ocr.py, selected with
config.OCR_ENGINE. It exposes the same interface (init_reader,
extract_plate_number, crop_plate, get_voted_text) and reuses ocr.py's plate
format rules, so the rest of the pipeline does not care which engine runs.

The recognizer reads ONE line of text, so the plate layout decides what it is fed:

    one row    "65 [flag] 12377"   the whole crop is one line; the flag usually
                                   reads as "=" and marks the 2|5 split
    two rows   "551 [flag] SYR"    each row is read on its own: the whole bottom
               "7467"              row, and the digit side of the top row

Feeding a two-row plate to the recognizer whole returns only the big bottom row
("5517467" -> "7467"), which is why a plain PaddleOCR run got every 3+4 plate wrong.

Both readings are tried, on the crop as detected and on a deskewed copy when the
plate is tilted, and the best-scoring valid plate wins.

Measured on TestingOCR(photos) -- 83 photos through YOLO, same boxes for both
engines. The constants below were tuned on this set, so treat it as a dev score:
    EasyOCR engine (ocr.py)          33 correct, 39 wrong, 11 unread
    this engine, PP-OCRv6_small_rec  80 correct,  0 wrong,  3 unread   ~70 ms/plate median (CPU)
On the 53 low-resolution manual_plate_crops (median width 62 px) it reads 37
correctly with 0 wrong, where the EasyOCR engine read 9 with 18 wrong.
"""
import math
import os
import re

import cv2
import numpy as np

# crop_plate and get_voted_text are engine-independent; re-exported so this
# module can stand in for ocr.py wherever the pipeline imports it.
from ocr import (  # noqa: F401
    FORMAT_CATEGORY,
    PREFIX_MISS_PENALTY,
    TEMPORARY,
    TEMPORARY_PREFIX,
    classify_format,
    crop_plate,
    get_voted_text,
)

_recognizer = None

# small kept the medium model's accuracy on full photos at ~1/10 of its CPU
# time; medium read a few more of the 53 tiny crops but takes ~0.7 s per plate.
DEFAULT_MODEL = "PP-OCRv6_small_rec"


def load_recognizer(model_name=DEFAULT_MODEL):
    # The models are cached after the first download; skip the slow startup
    # connectivity probe (downloads still work when a model is missing).
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import TextRecognition

    # Plain CPU kernels on 2 threads read faster than the default MKLDNN setup:
    # 69 vs 94 ms median, 150 vs 221 ms mean per plate on a 4-core i7-6820HQ,
    # with identical reads on both test sets.
    return TextRecognition(model_name=model_name, enable_mkldnn=False, cpu_threads=2)


def init_reader(recognizer):
    global _recognizer
    _recognizer = recognizer


def recognize(image):
    """Read one text line -> (text, score)."""
    if image is None or image.size == 0 or min(image.shape[:2]) < 4:
        return "", 0.0
    try:
        result = next(iter(_recognizer.predict(image)))
    except Exception as e:
        print("OCR ERROR:", e)
        return "", 0.0
    return result["rec_text"] or "", float(result["rec_score"] or 0.0)


def only_digits(text):
    return re.sub(r"\D", "", text or "")


# ============================================================
# PARSING  (pure functions: text + score in, plate + confidence out)
# ============================================================

PLATE_DIGITS = 7

# Length of the first group implied by the bottom row's digit count.
FIRST_LEN_BY_SECOND_LEN = {second: first for first, second in FORMAT_CATEGORY}

# The top row had more digits than its group needs (the flag's edge often reads
# as "1") -- the window picked from it is a guess, so it costs confidence.
TRIM_PENALTY = 0.85
# ...and worse when the top row alone is a valid group of the OTHER format
# ("333" above "14310"): the two rows contradict each other.
MISMATCH_PENALTY = 0.75


def parse_one_row(text, score):
    """Whole-plate read of a one-row plate -> (plate, conf) or None."""
    groups = re.findall(r"\d+", text or "")
    digits = "".join(groups)
    if len(digits) != PLATE_DIGITS:
        return None

    # The emblem usually reads as "=" or "-" and splits the groups for us. With
    # no usable split, fall back to 2+5: every one-row plate seen so far is 2+5.
    first_len = len(groups[0]) if len(groups) > 1 else 2
    if (first_len, PLATE_DIGITS - first_len) not in FORMAT_CATEGORY:
        first_len = 2

    first, second = digits[:first_len], digits[first_len:]
    return f"{first}-{second}", score * prefix_factor(first, second)


def parse_two_rows(top_text, top_score, bottom_text, bottom_score):
    """Separate reads of the top and bottom rows -> (plate, conf) or None."""
    top, bottom = only_digits(top_text), only_digits(bottom_text)

    # The bottom row is read whole and cleanly, so its length picks the format.
    first_len = FIRST_LEN_BY_SECOND_LEN.get(len(bottom))
    if first_len is None:
        return None
    first = pick_first_group(top, first_len)
    if first is None:
        return None

    conf = min(top_score, bottom_score)
    if len(top) != first_len:
        conf *= TRIM_PENALTY
        if len(top) in FIRST_LEN_BY_SECOND_LEN.values():
            conf *= MISMATCH_PENALTY
    return f"{first}-{bottom}", conf * prefix_factor(first, bottom)


def pick_first_group(top, length):
    """
    `length`-digit window from the top row's digits, or None.

    The digits sit on the left with the flag to their right, so the leftmost
    window is the default. For 3+4 the 5xx prior picks the window instead:
    a tilted top row read "6531" where the plate says 531.
    """
    if len(top) < length:
        return None
    windows = [top[i:i + length] for i in range(len(top) - length + 1)]
    if FORMAT_CATEGORY.get((length, PLATE_DIGITS - length)) == TEMPORARY:
        for window in windows:
            if window.startswith(TEMPORARY_PREFIX):
                return window
    return windows[0]


def prefix_factor(first, second):
    # Same 5xx prior as ocr.py, but only as a penalty: a bonus would push
    # competing reads to the 1.0 cap and make them impossible to rank.
    if classify_format(first, second) == TEMPORARY and not first.startswith(TEMPORARY_PREFIX):
        return PREFIX_MISS_PENALTY
    return 1.0


# ============================================================
# DESKEW
# ============================================================

# Plates photographed at an angle are the main source of misreads left: rows
# slant into each other, so a fixed row split cuts through digits.
MIN_DESKEW_ANGLE = 3.0      # below this, the tilt doesn't hurt the read
PREFER_DESKEW_ANGLE = 8.0   # above this, trust the straightened copy first
MAX_SKEW_ANGLE = 40.0


def estimate_skew(plate):
    """
    Plate tilt in degrees from its long straight edges (border, row lines).

    The plate edges are the longest lines in the crop; the diagonal hatching
    inside the digits only produces short ones, which minLineLength filters out.
    """
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    scale = 200.0 / max(h, w)
    gray = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30,
                            minLineLength=int(0.35 * gray.shape[1]), maxLineGap=6)
    if lines is None:
        return 0.0

    angles, lengths = [], []
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        angle = (angle + 90) % 180 - 90
        if abs(angle) <= MAX_SKEW_ANGLE:
            angles.append(angle)
            lengths.append(math.hypot(x2 - x1, y2 - y1))
    if not angles:
        return 0.0

    # Length-weighted median: robust to the odd stray line.
    order = np.argsort(angles)
    cumulative = np.cumsum(np.asarray(lengths)[order])
    return float(np.asarray(angles)[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def deskew(plate, angle):
    """Rotate the crop level and cut out the plate itself."""
    h, w = plate.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += new_w / 2 - w / 2
    matrix[1, 2] += new_h / 2 - h / 2
    # A flat fill: replicated borders smear into streaks the recognizer reads as digits.
    fill = tuple(int(v) for v in np.median(plate.reshape(-1, 3), axis=0))
    rotated = cv2.warpAffine(plate, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=fill)

    # The detection box is the axis-aligned bound of a plate W x H tilted by
    # `angle`: w = W cos + H sin, h = W sin + H cos. Solve for W, H and keep
    # just the plate -- on the whole rotated canvas the plate sits in a margin
    # of background, and the fixed row split no longer lands between the rows.
    denominator = cos * cos - sin * sin
    if denominator < 0.3:
        return rotated
    plate_w = (w * cos - h * sin) / denominator
    plate_h = (h * cos - w * sin) / denominator
    if plate_w < 0.4 * w or plate_h < 0.3 * h:
        return rotated
    plate_w, plate_h = min(new_w, plate_w * 1.08), min(new_h, plate_h * 1.08)
    x0, y0 = int((new_w - plate_w) / 2), int((new_h - plate_h) / 2)
    return rotated[y0:y0 + int(plate_h), x0:x0 + int(plate_w)]


# ============================================================
# READING
# ============================================================

# Two-row geometry: the bottom row starts a little above the middle, and the
# top row's digits sit on its left, before the flag and "SYR".
ROW_SPLIT = 0.42
ROW_OVERLAP = 0.05
TOP_DIGITS_RIGHT_EDGE = 0.55
# On two-row 2+5 plates "SYR" follows the two digits closely, and the
# recognizer's single score averages over those letters too: a clean "14" came
# back as "14 SYR" at 0.73 and was rejected. Just the digits end before this.
TOP_TWO_DIGITS_RIGHT_EDGE = 0.30


def read_one_row(view):
    parsed = parse_one_row(*recognize(view))
    return [parsed] if parsed else []


def read_two_rows(view):
    h, w = view.shape[:2]
    top_rows = view[:int(h * (ROW_SPLIT + ROW_OVERLAP))]
    bottom = recognize(view[int(h * ROW_SPLIT):, :])
    top = recognize(top_rows[:, :int(w * TOP_DIGITS_RIGHT_EDGE)])
    candidates = [parse_two_rows(*top, *bottom)]

    # The bottom row already says which format this is; for 2+5, re-read the
    # top row's digits without the "SYR" beside them.
    if FIRST_LEN_BY_SECOND_LEN.get(len(only_digits(bottom[0]))) == 2:
        digits_only = recognize(top_rows[:, :int(w * TOP_TWO_DIGITS_RIGHT_EDGE)])
        candidates.append(parse_two_rows(*digits_only, *bottom))
    return [candidate for candidate in candidates if candidate]


# A clean one-row read is final; the extra reads would only cost time.
EARLY_ACCEPT_CONF = 0.90

# Two different plates scoring within this margin of each other means the
# reads disagree, and the winner shouldn't keep its full confidence.
AMBIGUITY_MARGIN = 0.10
AMBIGUITY_PENALTY = 0.80

# A wrong plate number is worse than no plate number: it names an innocent
# vehicle in a security event. At 0.85 neither test set had a wrong read left
# (0/83 photos, 0/53 crops); on video the voting layer gets another chance anyway.
MIN_ACCEPT_CONF = 0.85


def read_plate(plate):
    """Best plate read, before the acceptance threshold -> (text, conf)."""
    views = [plate]
    angle = estimate_skew(plate)
    if abs(angle) >= MIN_DESKEW_ANGLE:
        straight = deskew(plate, angle)
        views = [straight, plate] if abs(angle) >= PREFER_DESKEW_ANGLE else [plate, straight]

    candidates = []
    for view in views:
        one_row = read_one_row(view)
        if one_row and one_row[0][1] >= EARLY_ACCEPT_CONF:
            return one_row[0]
        candidates += one_row + read_two_rows(view)

    if not candidates:
        return None, 0.0

    # max() keeps the first of equal scores, so the preferred view wins ties.
    text, conf = max(candidates, key=lambda c: c[1])
    rivals = [c for t, c in candidates if t != text]
    if rivals and max(rivals) >= conf - AMBIGUITY_MARGIN:
        conf *= AMBIGUITY_PENALTY
    return text, conf


def extract_plate_number(plate, min_conf=MIN_ACCEPT_CONF):
    """
    Returns (text, category, conf) like ocr.extract_plate_number.

    `min_conf` exists for evaluation: the best read does not depend on it, so
    running once with 0 and thresholding afterwards gives exactly what any
    threshold would have returned.
    """
    if _recognizer is None:
        raise RuntimeError("ocr_paddle.init_reader() must be called first")
    if plate is None or plate.size == 0:
        return None, None, 0.0

    text, conf = read_plate(plate)
    if not text or conf < min_conf:
        return None, None, 0.0
    first, second = text.split("-")
    return text, classify_format(first, second), min(conf, 1.0)
