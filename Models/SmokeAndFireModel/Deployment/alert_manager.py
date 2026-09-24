from collections import deque
import time

from config import (
  ALERT_REMINDER_SECONDS,
  ALERT_THRESHOLD,
  INCIDENT_CLEAR_SECONDS,
  WINDOW_MAX_AGE_SECONDS,
  WINDOW_SIZE,
)


class AlertManager:
  """Confirms detections over a sliding window and groups them into incidents.

  Each class keeps its own window of the last WINDOW_SIZE inference checks.
  Checks older than WINDOW_MAX_AGE_SECONDS are dropped, so a window never
  spans a stream outage. When a window reaches its class threshold an incident
  opens and one alert is raised; while it stays open a reminder is raised every
  ALERT_REMINDER_SECONDS. The incident closes once the class has gone
  undetected for INCIDENT_CLEAR_SECONDS, and the next confirmation opens a new
  one.

  Callers may attach evidence to each detected class. It is stored in the same
  window as the check it belongs to, so an alert only ever carries evidence
  from the checks that confirmed it.
  """

  def __init__(self):
    self.windows = {
      cls_name: deque(maxlen=WINDOW_SIZE)
      for cls_name in ALERT_THRESHOLD
    }
    self.incidents = {cls_name: None for cls_name in ALERT_THRESHOLD}

  def update(self, detected_classes, now=None, evidence=None):
    # Monotonic, not wall-clock: an NTP sync or clock change must not
    # shorten or stretch the windows and reminder intervals.
    if now is None:
      now = time.monotonic()
    evidence = evidence or {}

    alerts = []
    for cls_name, threshold in ALERT_THRESHOLD.items():
      detected = cls_name in detected_classes
      window = self.windows[cls_name]
      window.append((now, detected, evidence.get(cls_name) if detected else None))
      while now - window[0][0] > WINDOW_MAX_AGE_SECONDS:
        window.popleft()

      incident = self.incidents[cls_name]
      if incident is not None:
        if detected:
          incident['last_detected'] = now
        elif now - incident['last_detected'] >= INCIDENT_CLEAR_SECONDS:
          incident = self.incidents[cls_name] = None

      if len(window) < WINDOW_SIZE:
        continue

      positives = [(checked_at, item) for checked_at, hit, item in window if hit]
      if len(positives) < threshold:
        continue

      if incident is None:
        self.incidents[cls_name] = {
          'last_alert': now,
          'last_detected': positives[-1][0],
        }
        reminder = False
      elif now - incident['last_alert'] >= ALERT_REMINDER_SECONDS:
        incident['last_alert'] = now
        reminder = True
      else:
        continue

      alerts.append({
        'type': cls_name,
        'positive_checks': len(positives),
        'window_size': WINDOW_SIZE,
        'reminder': reminder,
        'evidence': [item for _, item in positives if item is not None],
      })

    return alerts
