import os

import cv2

import config

if config.SAVE_DEBUG:
    os.makedirs(config.DEBUG_FOLDER, exist_ok=True)

debug_counter = 0


def save_debug(plate, text, plate_type, track_id):
    global debug_counter
    if not config.SAVE_DEBUG or debug_counter >= config.MAX_DEBUG_IMAGES:
        return
    if plate is None or plate.size == 0:
        return
    debug_counter += 1
    if text is None:
        text = "NO_OCR"
    filename = f"plate_{debug_counter:03d}_id{track_id}_{plate_type}_{text}.jpg"
    cv2.imwrite(os.path.join(config.DEBUG_FOLDER, filename), plate)
