from collections import defaultdict

import cv2
import numpy as np

_reader = None


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

def run_ocr(image):
    if image is None or image.size == 0:
        return []

    h, w = image.shape[:2]
    if h < 5 or w < 5:
        return []

    scale = 5
    enlarged = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    enhanced = cv2.addWeighted(gray, 1.4, blur, -0.4, 0)

    try:
        results = _reader.readtext(
            enhanced,
            allowlist="0123456789",
            detail=1,
            paragraph=False,
            text_threshold=0.35,
            low_text=0.25,
            link_threshold=0.20,
            width_ths=0.5,
            decoder="greedy"
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
        center_x = sum(p[0] for p in box) / len(box)
        center_y = sum(p[1] for p in box) / len(box)
        detections.append({"text": digits, "conf": float(conf), "x": center_x, "y": center_y})

    return detections


# ============================================================
# DETERMINE PLATE TYPE
# ============================================================

def get_plate_type(width, height):
    if height <= 0:
        return "vertical"
    ratio = width / float(height)
    return "rectangle" if ratio >= 1.6 else "vertical"


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
# RECTANGLE PLATE:  15 | 14193
# ============================================================

def extract_rectangle(plate):
    h, w = plate.shape[:2]
    plate = cv2.resize(plate, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    h, w = plate.shape[:2]

    left = plate[int(h * 0.08):int(h * 0.92), int(w * 0.02):int(w * 0.30)]
    right = plate[int(h * 0.08):int(h * 0.92), int(w * 0.32):int(w * 0.98)]

    left_results = run_ocr(left)
    right_results = run_ocr(right)

    left_results.sort(key=lambda x: x["x"])
    right_results.sort(key=lambda x: x["x"])

    first_candidates = []
    for item in left_results:
        first_candidates.extend(pick_best_window(item["text"], 2, item["conf"]))
    if not first_candidates:
        left_text = "".join(item["text"] for item in left_results)
        first_candidates.extend(pick_best_window(left_text, 2, 0.40))

    first = None
    if first_candidates:
        first_candidates.sort(key=lambda x: x[1], reverse=True)
        first = first_candidates[0][0]

    second_candidates = []
    for item in right_results:
        second_candidates.extend(pick_best_window(item["text"], 5, item["conf"]))
    if not second_candidates:
        right_text = "".join(item["text"] for item in right_results)
        second_candidates.extend(pick_best_window(right_text, 5, 0.40))

    second = None
    if second_candidates:
        second_candidates.sort(key=lambda x: x[1], reverse=True)
        second = second_candidates[0][0]

    if first is not None and second is not None:
        if len(first) == 2 and len(second) == 5:
            avg_conf = (first_candidates[0][1] + second_candidates[0][1]) / 2
            return f"{first}-{second}", avg_conf

    return None, 0.0


# ============================================================
# VERTICAL PLATE:  541 / 5134
# ============================================================

def extract_vertical(plate):
    h, w = plate.shape[:2]
    plate = cv2.resize(plate, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    h, w = plate.shape[:2]

    top = plate[int(h * 0.04):int(h * 0.48), int(w * 0.05):int(w * 0.95)]
    bottom = plate[int(h * 0.43):int(h * 0.97), int(w * 0.05):int(w * 0.95)]

    top_results = run_ocr(top)
    bottom_results = run_ocr(bottom)

    top_results.sort(key=lambda x: x["x"])
    bottom_results.sort(key=lambda x: x["x"])

    top_text = "".join(item["text"] for item in top_results)
    bottom_text = "".join(item["text"] for item in bottom_results)

    top_conf = np.mean([item["conf"] for item in top_results]) if top_results else 0.4
    bottom_conf = np.mean([item["conf"] for item in bottom_results]) if bottom_results else 0.4

    first = top_text[:3] if len(top_text) >= 3 else None
    second = bottom_text[:4] if len(bottom_text) >= 4 else None

    if first is not None and second is not None:
        if len(first) == 3 and len(second) == 4:
            return f"{first}-{second}", (top_conf + bottom_conf) / 2

    return None, 0.0


# ============================================================
# EXTRACT PLATE NUMBER
# ============================================================

def extract_plate_number(plate):
    if plate is None or plate.size == 0:
        return None, None, 0.0

    h, w = plate.shape[:2]
    plate_type = get_plate_type(w, h)

    if plate_type == "rectangle":
        text, conf = extract_rectangle(plate)
    else:
        text, conf = extract_vertical(plate)

    return text, plate_type, conf


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
