import easyocr
from ultralytics import YOLO

import config


def load_models():
    print("=" * 70)
    print("Loading EasyOCR...")
    reader = easyocr.Reader(['en'], gpu=config.USE_GPU, verbose=True)
    print("EasyOCR loaded.")

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
