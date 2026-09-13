import cv2
import threading
import time


class VideoSource:
  def __init__(self, source=0):
    if isinstance(source, int):
      self.capture = cv2.VideoCapture(source, cv2.CAP_DSHOW)
      if not self.capture.isOpened():
        self.capture.release()
        self.capture = cv2.VideoCapture(source)
    else:
      self.capture = cv2.VideoCapture(source)
    self.condition = threading.Condition()
    self.latest_frame = None
    self.frame_id = 0
    self.last_read_id = 0
    self.stopped = False
    self.thread = threading.Thread(target=self._update, daemon=True)
    self.thread.start()

  def _update(self):
    failed_reads = 0
    while not self.stopped:
      success, frame = self.capture.read()
      if not success:
        failed_reads += 1
        if failed_reads < 10:
          time.sleep(0.01)
          continue
        with self.condition:
          self.stopped = True
          self.condition.notify_all()
        return

      failed_reads = 0

      with self.condition:
        self.latest_frame = frame
        self.frame_id += 1
        self.condition.notify_all()

  def read(self):
    with self.condition:
      self.condition.wait_for(
        lambda: self.frame_id > self.last_read_id or self.stopped,
        timeout=1,
      )
      if self.frame_id == self.last_read_id:
        return False, None

      self.last_read_id = self.frame_id
      return True, self.latest_frame.copy()

  def is_opened(self):
    return self.capture.isOpened() and not self.stopped

  def release(self):
    self.stopped = True
    with self.condition:
      self.condition.notify_all()
    self.capture.release()
    self.thread.join(timeout=1)
