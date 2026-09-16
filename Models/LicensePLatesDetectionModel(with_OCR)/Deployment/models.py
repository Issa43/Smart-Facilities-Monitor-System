import os

import config

# Avoid PyTorch/OpenMP thread contention during EasyOCR inference on Windows.
# Not for Paddle: a single thread made its recognizer ~5x slower.
if config.OCR_ENGINE == "easyocr":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

import torch
from ultralytics import YOLO


def load_ocr_reader():
    if config.OCR_ENGINE == "paddle":
        import ocr_paddle
        print(f"Loading PaddleOCR ({config.PADDLE_REC_MODEL})...")
        return ocr_paddle.load_recognizer(config.PADDLE_REC_MODEL)

    import easyocr
    print("Loading EasyOCR...")
    return easyocr.Reader(['en'], gpu=config.USE_GPU, verbose=True)


def load_models():
    torch.set_num_threads(1)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    print("=" * 70)
    reader = load_ocr_reader()
    print("OCR loaded.")

    print("=" * 70)
    print("Loading Plate YOLO...")
    model = YOLO(config.MODEL_PATH)
    print("Plate YOLO loaded.")
    print("Classes:", model.names)

    print("=" * 70)
    print("Loading Vehicle YOLO (COCO)...")
    vehicle_model = YOLO(config.VEHICLE_MODEL_PATH)
    print("Vehicle YOLO loaded.")
    print("=" * 70)

    return reader, model, vehicle_model
