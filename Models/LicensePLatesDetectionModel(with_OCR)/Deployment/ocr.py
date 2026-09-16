from collections import defaultdict

import cv2
import numpy as np

_reader = None

OCR_TARGET_HEIGHT = 300
MAX_UPSCALE = 5.0


def init_reader(reader):
    global _reader
    _reader = reader


# ============================================================
# CLEAN OCR TEXT
# ============================================================

def clean_digits(text):
    if text is None:
        return ""
    return "".join(c for c in text if c.isdigit())


# ============================================================
# OCR FUNCTION
# ============================================================

# Low thresholds help tiny, blurry video crops but on a sharp close-up they merge
# the holographic border and the flag into fake digits; EasyOCR's defaults don't.
TUNED_THRESHOLDS = dict(text_threshold=0.35, low_text=0.25, link_threshold=0.20)
DEFAULT_THRESHOLDS = dict(text_threshold=0.7, low_text=0.4, link_threshold=0.4)
SMALL_PLATE_THRESHOLDS = dict(text_threshold=0.15, low_text=0.10, link_threshold=0.10)


def run_ocr(image, enhance=True, thresholds=TUNED_THRESHOLDS):
    if image is None or image.size == 0:
        return []

    gray = prepare_ocr_image(image, enhance=enhance)
    if gray is None:
        return []

    try:
        results = _reader.readtext(
            gray,
            allowlist="0123456789",
            detail=1,
            paragraph=False,
            width_ths=0.5,
            decoder="greedy",
            **thresholds
        )
    except Exception as e:
        print("OCR ERROR:", e)
        return []

    detections = []
    for box, text, conf in results:
        if conf < 0.20:
            continue
        digits = clean_digits(text)
        if not digits:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        detections.append({
            "text": digits,
            "conf": float(conf),
            "x": sum(xs) / len(xs),
            "y": sum(ys) / len(ys),
            "x1": min(xs), "x2": max(xs),
            "y1": min(ys), "y2": max(ys),
        })

    return drop_small_print(detections)


def prepare_ocr_image(image, enhance=True):
    """Create the same upscaled grayscale image that EasyOCR receives."""
    if image is None or image.size == 0:
        return None

    h, w = image.shape[:2]
    if h < 5 or w < 5:
        return None

    scale = min(MAX_UPSCALE, max(1.0, OCR_TARGET_HEIGHT / h))
    enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)

    if enhance:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
        gray = cv2.addWeighted(gray, 1.4, blur, -0.4, 0)

    return gray


def run_row_ocr(row):
    """
    Read a plate row, trying the strictest thresholds first.

    Measured on the Square.jpg crop, bottom row (true value 5950):
        default -> 5950 (conf 0.97)      <- correct
        tuned   -> 5250 / 6250
        small   -> 6250
    The loose thresholds were tried first and their wrong answer won, which is
    what produced the 631-6250 misread. They still earn their place as a
    fallback for genuinely tiny video crops, just not as the first choice.
    """
    for thresholds in (DEFAULT_THRESHOLDS, TUNED_THRESHOLDS, SMALL_PLATE_THRESHOLDS):
        detections = run_ocr(row, thresholds=thresholds)
        if detections:
            return detections

    gray = cv2.cvtColor(row, cv2.COLOR_BGR2GRAY)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    for view in (otsu, adaptive):
        detections = run_ocr(
            cv2.cvtColor(view, cv2.COLOR_GRAY2BGR),
            thresholds=SMALL_PLATE_THRESHOLDS,
        )
        if detections:
            return detections
    return []


def drop_small_print(detections, min_ratio=0.4):
    """Drop serial numbers and fine print that sit well below the plate digits' height."""
    if not detections:
        return detections
    tallest = max(d["y2"] - d["y1"] for d in detections)
    return [d for d in detections if d["y2"] - d["y1"] >= tallest * min_ratio]


# ============================================================
# GROUP DIGITS BY THE WIDEST GAP
# ============================================================

def split_at_largest_gap(items, axis):
    """
    Split detections into two groups at the widest blank gap along `axis`.

    Locates the real separator (the emblem, or the row break) from the image
    instead of assuming it sits at a fixed percentage of the plate.
    """
    if len(items) < 2:
        return list(items), []

    lo, hi = ("x1", "x2") if axis == "x" else ("y1", "y2")
    ordered = sorted(items, key=lambda d: d[lo])

    best_i = 0
    best_gap = None
    for i in range(len(ordered) - 1):
        gap = ordered[i + 1][lo] - ordered[i][hi]
        if best_gap is None or gap > best_gap:
            best_gap = gap
            best_i = i

    return ordered[:best_i + 1], ordered[best_i + 1:]


def read_in_order(items):
    return "".join(d["text"] for d in sorted(items, key=lambda d: d["x1"]))


def rows_are_separate(items):
    """True when the digits form two rows (e.g. a wide "01 / 12350" plate)."""
    top, bottom = split_at_largest_gap(items, "y")
    if not top or not bottom:
        return False
    # Detection boxes are padded, so compare centres against the other row's edge.
    return (min(d["y"] for d in bottom) > max(d["y2"] for d in top)
            and max(d["y"] for d in top) < min(d["y1"] for d in bottom))


def comes_before(a, b):
    """a reads before b: to its left on the same row, or on the row above."""
    return a["x"] < b["x1"] or a["y"] < b["y1"]


def pick_by_format(items, first_len, second_len):
    """
    Pick the best detection that is exactly `first_len` digits and the best one
    that is exactly `second_len` digits, in reading order. Stray reads from the
    flag, the "SYR" block or the serial number rarely match both lengths.
    """
    firsts = [d for d in items if len(d["text"]) == first_len]
    seconds = [d for d in items if len(d["text"]) == second_len]

    best = None
    for a in firsts:
        for b in seconds:
            if a is b or not comes_before(a, b):
                continue
            conf = (a["conf"] + b["conf"]) / 2
            if best is None or conf > best[2]:
                best = (a["text"], b["text"], conf)

    return best or (None, None, 0.0)


def assemble_plate(items, axis="auto", formats=None):
    """
    Read a plate from OCR detections: layout decides the split axis, and where
    the split actually lands decides the format.

    Both Syrian formats are 7 digits (2+5 and 3+4), so the digit count validates
    the read while the separator position -- found from the image by
    split_at_largest_gap, not assumed -- tells the two formats apart.
    """
    if not items:
        return None, None, 0.0

    if axis in ("auto", "x") and rows_are_separate(items):
        axis = "y"
    elif axis == "auto":
        axis = "x"

    group_a, group_b = split_at_largest_gap(items, axis)
    first = read_in_order(group_a)
    second = read_in_order(group_b)
    base_conf = float(np.mean([d["conf"] for d in items]))

    return score_pair(first, second, base_conf, formats)


# ============================================================
# PLATE FORMAT  (what the digit groups mean)
# ============================================================

# Syrian plates come as "12 | 34567" or "123 | 4567", on one row or two, so the
# box's aspect ratio doesn't say which format it is -- the digit groups do.
PLATE_FORMATS = [(2, 5), (3, 4)]

PERMANENT = "permanent"                  # 2+5 -- fully cleared vehicle
TEMPORARY = "temporary_customs"          # 3+4 -- customs pending, plate valid 3 months

FORMAT_CATEGORY = {(2, 5): PERMANENT, (3, 4): TEMPORARY}

# Temporary plates nearly always start with 5. Treated as a prior that adjusts
# confidence -- never as a filter, because a hard filter both discards valid
# non-5 plates and can actively select a misread window that happens to start
# with 5 over the correct one.
#
# Measured on the 53-crop labeled set: all 14 temporary (3+4) plates start
# with 5, but so does one PERMANENT plate -- 5418570 reads "54 | 18570" on a
# single row. So "5xx means temporary" is a strong prior, not a rule. The
# prefix is only consulted while testing the 3+4 hypothesis, which is why that
# counterexample does not break it; don't tighten this into a rule later.
TEMPORARY_PREFIX = "5"
PREFIX_MATCH_BONUS = 1.10
PREFIX_MISS_PENALTY = 0.85


def classify_format(first, second):
    """Category for a digit-group pair, or None when it matches no known format."""
    return FORMAT_CATEGORY.get((len(first), len(second)))


def score_pair(first, second, base_conf, formats=None):
    """Validate a (first, second) digit pair against the plate formats."""
    if not first or not second:
        return None, None, 0.0

    lengths = (len(first), len(second))
    if formats is not None and lengths not in formats:
        return None, None, 0.0

    category = classify_format(first, second)
    if category is None:
        return None, None, 0.0

    conf = base_conf
    if category == TEMPORARY:
        conf *= PREFIX_MATCH_BONUS if first.startswith(TEMPORARY_PREFIX) else PREFIX_MISS_PENALTY

    return f"{first}-{second}", category, min(conf, 1.0)


# ============================================================
# LAYOUT HINT  (only decides which reading attempt to try first)
# ============================================================

# A wide box is usually a one-row plate, but this is a weak hint about LAYOUT
# only. It says nothing about the digit format: measured on real photos, a
# two-row 3+4 plate came in at ratio 1.68 while a two-row 2+5 plate measured
# 1.96 -- so no ratio threshold can separate the formats.
ONE_ROW_MIN_RATIO = 2.50


def layout_hint(width, height):
    if height <= 0:
        return "two_row"
    return "one_row" if width / float(height) >= ONE_ROW_MIN_RATIO else "two_row"


# ============================================================
# CROP PLATE
# ============================================================

def crop_plate(frame, x1, y1, x2, y2):
    h, w = frame.shape[:2]
    box_w = x2 - x1
    box_h = y2 - y1

    pad_x = max(3, int(box_w * 0.06))
    pad_y = max(3, int(box_h * 0.06))

    xx1 = max(0, x1 - pad_x)
    yy1 = max(0, y1 - pad_y)
    xx2 = min(w, x2 + pad_x)
    yy2 = min(h, y2 + pad_y)

    return frame[yy1:yy2, xx1:xx2]


# ============================================================
# HELPER: pick the best substring window
# ============================================================

def pick_best_window(text, target_len, base_conf):
    if len(text) == target_len:
        return [(text, base_conf)]
    if len(text) < target_len:
        return []

    candidates = []
    for i in range(len(text) - target_len + 1):
        window = text[i:i + target_len]
        penalty = 1.0 - (0.05 * i)
        candidates.append((window, base_conf * max(0.3, penalty)))
    return candidates


# ============================================================
# WHOLE-PLATE READ
# ============================================================

def read_whole_plate(plate, formats=None):
    """Plain, default-threshold read of the whole plate, kept only on an exact format match."""
    items = run_ocr(plate, enhance=False, thresholds=DEFAULT_THRESHOLDS)

    best = (None, None, 0.0)
    for first_len, second_len in (formats or PLATE_FORMATS):
        first, second, conf = pick_by_format(items, first_len, second_len)
        if not first:
            continue
        text, category, scored = score_pair(first, second, conf)
        if text and scored > best[2]:
            best = (text, category, scored)
    return best


# ============================================================
# ONE-ROW PLATE:  19 | 13058
# ============================================================

# Where the emblem sits, as a fraction of plate width, per format.
#
# Only 2+5 is listed. Every one-row plate seen so far is 2+5; 3+4 has only ever
# appeared as a two-row plate. Adding a guessed 3+4 split here made Rectangle.jpg
# return a confident "771-1030" instead of failing cleanly -- invented crop
# geometry manufactures readings. A one-row 3+4 plate, if one exists, is still
# reachable through the gap-based path, which measures the separator instead of
# assuming it.
ONE_ROW_SPLITS = {(2, 5): (0.30, 0.32)}


def extract_one_row(plate):
    # Tight per-group crops read more accurately, so they stay the primary path;
    # the gap-based pass only runs when they fail (e.g. a plate layout whose
    # separator doesn't sit where the fixed crops assume).
    text, category, conf = extract_one_row_fixed(plate)
    if text:
        return text, category, conf

    scaled = cv2.resize(plate, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    h, w = scaled.shape[:2]
    body = scaled[int(h * 0.08):int(h * 0.92), int(w * 0.02):int(w * 0.98)]
    return assemble_plate(run_ocr(body), "auto")


def extract_one_row_fixed(plate):
    """Try each format's expected emblem position; keep the best complete read."""
    plate = cv2.resize(plate, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    h, w = plate.shape[:2]

    best = (None, None, 0.0)
    for (first_len, second_len), (left_end, right_start) in ONE_ROW_SPLITS.items():
        left = plate[int(h * 0.08):int(h * 0.92), int(w * 0.02):int(w * left_end)]
        right = plate[int(h * 0.08):int(h * 0.92), int(w * right_start):int(w * 0.98)]

        # run_row_ocr, not run_ocr: the same strict-thresholds-first ladder the
        # two-row path uses. With raw run_ocr (tuned) the 5-digit group on
        # Rectangle.jpg returned nothing at all.
        first, first_conf = best_group(run_row_ocr(left), first_len)
        second, second_conf = best_group(run_row_ocr(right), second_len)
        if first is None or second is None:
            continue

        text, category, conf = score_pair(first, second, (first_conf + second_conf) / 2)
        if text and conf > best[2]:
            best = (text, category, conf)

    return best


# ============================================================
# TWO-ROW PLATE:  14 / 67232   or   531 / 5950
# ============================================================

def extract_two_row(plate):
    text, category, conf = extract_two_row_fixed(plate)
    if text:
        return text, category, conf

    scaled = cv2.resize(plate, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    h, w = scaled.shape[:2]
    body = scaled[int(h * 0.04):int(h * 0.97), int(w * 0.05):int(w * 0.95)]
    return assemble_plate(run_ocr(body), "y")


# On both two-row layouts the number group sits on the LEFT of the top row and
# the flag / "SYR" / "سورية" block on the right, which OCR happily turns into
# extra digits. Narrowing the top row to the digit side removes that source.
# Measured on Square.jpg, top row (true value 531):
#     x 0.05..0.95 -> 7531383      (emblem read as digits)
#     x 0.05..0.48 -> 531          (conf 0.81)
TOP_ROW_RIGHT_EDGES = (0.48, 0.62, 0.95)


def extract_two_row_fixed(plate):
    """
    Read the two rows, then try both formats against them.

    The row split serves 2+5 and 3+4 alike -- only the expected group lengths
    differ, so the same crops answer both.
    """
    plate = cv2.resize(plate, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    h, w = plate.shape[:2]

    # Keep a small overlap so characters near the row boundary are not clipped
    # by interpolation on very small plate crops.
    bottom = plate[int(h * 0.43):int(h * 0.97), int(w * 0.05):int(w * 0.95)]
    bottom_results = run_row_ocr(bottom)
    if not bottom_results:
        # A row that read nothing cannot be rescued by an assumed confidence.
        return None, None, 0.0

    best = (None, None, 0.0)
    for right_edge in TOP_ROW_RIGHT_EDGES:
        top = plate[int(h * 0.04):int(h * 0.48), int(w * 0.05):int(w * right_edge)]
        top_results = run_row_ocr(top)
        if not top_results:
            continue

        for first_len, second_len in PLATE_FORMATS:
            # The 5xx prior helps CHOOSE the first group, not just score it
            # afterwards -- otherwise a stray leading digit ("5313" -> "313")
            # or a misread ("631") can win on position or raw confidence alone.
            prefer = TEMPORARY_PREFIX if first_len == 3 else None
            first, first_conf = best_group(top_results, first_len, prefer_prefix=prefer)
            second, second_conf = best_group(bottom_results, second_len)
            if first is None or second is None:
                continue

            text, category, conf = score_pair(first, second, (first_conf + second_conf) / 2)
            if text and conf > best[2]:
                best = (text, category, conf)

    return best


def best_group(results, target_len, prefer_prefix=None):
    """
    Best `target_len`-digit window across a row's detections, or None.

    `prefer_prefix` nudges the choice toward windows starting with it (the 5xx
    convention on temporary plates). It is a weight, not a filter: a window that
    does not match stays in the running and can still win.
    """
    if not results:
        return None, 0.0

    results = sorted(results, key=lambda d: d["x"])

    candidates = []
    for item in results:
        candidates.extend(pick_best_window(item["text"], target_len, item["conf"]))
    if not candidates:
        joined = "".join(item["text"] for item in results)
        mean_conf = float(np.mean([item["conf"] for item in results]))
        candidates = pick_best_window(joined, target_len, mean_conf)
    if not candidates:
        return None, 0.0

    if prefer_prefix:
        candidates = [
            (text, conf * (PREFIX_MATCH_BONUS if text.startswith(prefer_prefix)
                           else PREFIX_MISS_PENALTY))
            for text, conf in candidates
        ]

    return max(candidates, key=lambda c: c[1])


# ============================================================
# EXTRACT PLATE NUMBER
# ============================================================

# A wrong plate number is worse than no plate number: it names an innocent
# vehicle in a security event. Reads below this confidence are discarded, and
# on video the voting layer gets another chance on the next frame anyway.
MIN_ACCEPT_CONF = 0.45


def extract_plate_number(plate):
    """
    Returns (text, category, conf).

    `category` is PERMANENT (2+5, cleared vehicle) or TEMPORARY (3+4, customs
    pending on a plate valid 3 months) -- derived from the digit format, so it
    comes free with the read and belongs on the event record.
    """
    if plate is None or plate.size == 0:
        return None, None, 0.0

    h, w = plate.shape[:2]

    # A sharp close-up usually resolves in one plain read.
    attempts = [read_whole_plate]

    # Then the layout the box shape suggests, then the other one -- the hint
    # only orders the attempts, it never decides the format.
    if layout_hint(w, h) == "one_row":
        attempts += [extract_one_row, extract_two_row]
    else:
        attempts += [extract_two_row, extract_one_row]

    for attempt in attempts:
        text, category, conf = attempt(plate)
        if text and conf >= MIN_ACCEPT_CONF:
            return text, category, conf

    return None, None, 0.0


# ============================================================
# WEIGHTED VOTING
# ============================================================

def get_voted_text(history, min_votes):
    if not history:
        return None, 0

    scores = defaultdict(float)
    counts = defaultdict(int)
    for text, conf in history:
        scores[text] += conf
        counts[text] += 1

    best_text = max(scores, key=scores.get)
    votes = counts[best_text]

    if votes >= min_votes:
        return best_text, votes
    return None, votes
