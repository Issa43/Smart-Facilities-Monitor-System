import json
import queue
import threading
from urllib import request
from urllib.error import HTTPError, URLError

class AlertNotifier:
  def __init__(self, alert_url=None, timeout=5):
    self.alert_url = alert_url
    self.timeout = timeout
    self.alert_queue = queue.Queue()
    self.stopped = False
    self.thread = None
    if self.alert_url:
      self.thread = threading.Thread(target=self._worker, daemon=True)
      self.thread.start()

  def _worker(self):
    while True:
      alert = self.alert_queue.get()
      if alert is None:
        self.alert_queue.task_done()
        return
      try:
        self._send_now(alert)
      finally:
        self.alert_queue.task_done()

  def _send_now(self, alert):
    payload = json.dumps(alert).encode('utf-8')
    http_request = request.Request(
      self.alert_url,
      data=payload,
      headers={'Content-Type': 'application/json'},
      method='POST',
    )

    try:
      with request.urlopen(
        http_request,
        timeout=self.timeout,
      ) as response:
        pass
    except HTTPError as error:
      print(f'HTTP error: {error.code}')
    except URLError as error:
      print(f'Connection error: {error.reason}')
    except TimeoutError:
      print('The request timed out')

  def send(self, alert):
    if not self.alert_url:
      return
    self.alert_queue.put_nowait(alert)

  def close(self):
    if not self.thread:
      return
    self.stopped = True
    self.alert_queue.put(None)
    self.thread.join(timeout=self.timeout + 1)