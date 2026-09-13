from ultralytics import YOLO

from config import CONF_THRESHOLD, DEVICE, IMAGE_SIZE, MODEL_PATH


class Detector:
  def __init__(self, model_path=MODEL_PATH, device=DEVICE):
    self.model = YOLO(model_path, task='detect')
    self.device = device

  def detect(self, frame, roi=None):
    results = self.model(
      frame,
      conf=CONF_THRESHOLD,
      device=self.device,
      imgsz=IMAGE_SIZE,
      verbose=False,
    )
    detections = []

    for box in results[0].boxes:
      class_name = self.model.names[int(box.cls)]
      confidence = float(box.conf[0])
      coordinates = tuple(map(int, box.xyxy[0].tolist()))

      if roi and not self._is_inside_roi(coordinates, roi):
        continue

      detections.append({
        'class_name': class_name,
        'confidence': confidence,
        'box': coordinates,
      })

    return detections

  @staticmethod
  def _is_inside_roi(box, roi):
    x1, y1, x2, y2 = box
    rx, ry, rw, rh = roi
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    return rx <= center_x <= rx + rw and ry <= center_y <= ry + rh