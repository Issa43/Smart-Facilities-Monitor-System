from collections import deque
import time

from config import ALERT_THRESHOLD, COOLDOWN_SECONDS, WINDOW_SIZE


class AlertManager:
  def __init__(self):
    self.windows = {
      cls_name: deque(maxlen=WINDOW_SIZE)
      for cls_name in ALERT_THRESHOLD
    }
    self.last_alert_time = {
      cls_name: 0 for cls_name in ALERT_THRESHOLD
    }

  def update(self, detected_classes, now=None):
    if now is None:
      now = time.time()

    alerts = []
    for cls_name, threshold in ALERT_THRESHOLD.items():
      window = self.windows[cls_name]
      window.append(1 if cls_name in detected_classes else 0)

      if len(window) < WINDOW_SIZE:
        continue

      positive_count = sum(window)
      in_cooldown = (
        now - self.last_alert_time[cls_name] < COOLDOWN_SECONDS
      )

      if positive_count >= threshold and not in_cooldown:
        alerts.append({
          'type': cls_name,
          'positive_checks': positive_count,
          'window_size': WINDOW_SIZE,
        })
        self.last_alert_time[cls_name] = now

    return alerts