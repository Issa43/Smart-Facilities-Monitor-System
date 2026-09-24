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
    self.frame_interval = self._file_frame_interval(source)
    self.condition = threading.Condition()
    self.latest_frame = None
    self.frame_id = 0
    self.last_read_id = 0
    self.stopped = False
    self.thread = threading.Thread(target=self._update, daemon=True)
    self.thread.start()

  def _file_frame_interval(self, source):
    """Seconds per frame for a video file, or 0 for a live source.

    A camera or stream delivers frames in real time on its own. A file is
    decoded as fast as the CPU allows -- several times real time -- which makes
    the alert timings (window age, incident clear, reminders) behave differently
    from a live camera. Pacing a file to its own frame rate keeps them equal.
    """
    if isinstance(source, int) or '://' in str(source):
      return 0
    fps = self.capture.get(cv2.CAP_PROP_FPS)
    return 1 / fps if fps and fps > 0 else 0

  def _update(self):
    failed_reads = 0
    next_frame_at = time.monotonic()
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

      if self.frame_interval:
        next_frame_at += self.frame_interval
        delay = next_frame_at - time.monotonic()
        if delay > 0:
          time.sleep(delay)
        else:
          # Decoding fell behind; carry on from now rather than rushing
          # through frames to catch up.
          next_frame_at = time.monotonic()

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
