import cv2
import subprocess
import threading
import time
from collections import deque

from alert_manager import AlertManager
from config import BACKEND_ALERT_URL, DEVICE, FRAME_SKIP, MODEL_PATH, VIDEO_SOURCE
from detector import Detector
from notifier import AlertNotifier
from video_source import VideoSource


def get_gpu_usage():
  try:
    output = subprocess.check_output(
      [
        'nvidia-smi',
        '--query-gpu=utilization.gpu,memory.used,memory.total',
        '--format=csv,noheader,nounits',
      ],
      text=True,
      stderr=subprocess.DEVNULL,
    ).strip()
    usage, memory_used, memory_total = output.split(',')
    return f'GPU: {usage.strip()}% | VRAM: {memory_used.strip()}/{memory_total.strip()} MB'
  except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
    return 'GPU: N/A'


class GpuMonitor:
  def __init__(self, interval=1):
    self.interval = interval
    self.text = 'GPU: N/A'
    self.lock = threading.Lock()
    self.stop_event = threading.Event()
    self.thread = threading.Thread(target=self._update, daemon=True)
    self.thread.start()

  def _update(self):
    while not self.stop_event.is_set():
      current_text = get_gpu_usage()
      with self.lock:
        self.text = current_text
      self.stop_event.wait(self.interval)

  def get(self):
    with self.lock:
      return self.text

  def close(self):
    self.stop_event.set()
    self.thread.join(timeout=self.interval + 1)


def draw_detections(frame, detections):
  for detection in detections:
    class_name = detection['class_name']
    confidence = detection['confidence']
    x1, y1, x2, y2 = detection['box']
    box_color = (0, 0, 255) if class_name == 'Fire' else (255, 165, 0)
    label = f'{class_name} {confidence:.2f}'

    cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
    cv2.putText(
      frame,
      label,
      (x1, max(y1 - 10, 20)),
      cv2.FONT_HERSHEY_SIMPLEX,
      0.6,
      box_color,
      2,
      cv2.LINE_AA,
    )


def main():
  detector = Detector(MODEL_PATH, DEVICE)
  alert_manager = AlertManager()
  notifier = AlertNotifier(BACKEND_ALERT_URL)
  video_source = VideoSource(VIDEO_SOURCE)

  success, first_frame = video_source.read()
  if not success:
    print('Failed to read from the video stream')
    video_source.release()
    return

  roi = cv2.selectROI(
    'Select Alert Region', first_frame, fromCenter=False, showCrosshair=True
  )
  cv2.destroyWindow('Select Alert Region')
  has_roi = roi[2] > 0 and roi[3] > 0
  gpu_monitor = GpuMonitor()
  cv2.namedWindow('Detection', cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
  cv2.resizeWindow('Detection', 1280, 720)

  frame_count = 0
  detections = []
  display_times = deque(maxlen=30)
  try:
    while video_source.is_opened():
      success, frame = video_source.read()
      if not success:
        break

      frame_count += 1
      if frame_count % FRAME_SKIP == 0:
        detections = detector.detect(frame, roi if has_roi else None)
        detected_classes = {item['class_name'] for item in detections}

        for alert in alert_manager.update(detected_classes):
          notifier.send(alert)
          print(
            f"Alert: {alert['type']}! ({alert['positive_checks']}/"
            f"{alert['window_size']} positive checks)"
          )

      draw_detections(frame, detections)

      if has_roi:
        rx, ry, rw, rh = roi
        cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2)

      current_time = time.perf_counter()
      display_times.append(current_time)
      if len(display_times) > 1:
        elapsed = display_times[-1] - display_times[0]
        fps = (len(display_times) - 1) / max(elapsed, 1e-6)
      else:
        fps = 0.0

      cv2.putText(
        frame,
        f'FPS: {fps:.1f}',
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
      )
      cv2.putText(
        frame,
        gpu_monitor.get(),
        (10, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
      )

      cv2.imshow('Detection', frame)
      if cv2.waitKey(1) & 0xFF == ord('q'):
        break
  finally:
    video_source.release()
    notifier.close()
    gpu_monitor.close()
    cv2.destroyAllWindows()


if __name__ == '__main__':
  main()