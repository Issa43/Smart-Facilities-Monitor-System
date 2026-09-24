"""What the SFLMS admin console has configured for this detector's camera.

The admin switches AI models on and off per camera and draws ROIs on it. The
detector polls those settings in the background, so a change takes effect
within CONFIG_REFRESH_SECONDS without restarting anything. When the backend
cannot be reached the last known settings stay in force.

The fire/smoke and intrusion detectors each keep an identical copy of this file,
because each is built as its own container.
"""

import json
import os
import threading
from urllib import request
from urllib.error import HTTPError, URLError


class CameraSettings:
    def __init__(self, config, model_identifier, *, with_rois=False):
        self.config = config
        self.model_identifier = model_identifier
        self.with_rois = with_rois
        self.refresh_seconds = float(os.environ.get("CONFIG_REFRESH_SECONDS", "30"))
        self.api_base = config.api_url.rsplit("camera-events", 1)[0]
        # Until the backend answers, assume the model is on: a detector that
        # cannot reach its configuration should not silently stop watching.
        self.model_enabled = True
        self.rois = []
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.refresh()
        self._thread.start()
        return self

    def close(self):
        self._stopped.set()

    def _run(self):
        while not self._stopped.wait(self.refresh_seconds):
            self.refresh()

    def refresh(self):
        try:
            models = self._get(f"cameras/{self.config.camera_id}/active-models/")
            enabled = any(
                item.get("model_identifier") == self.model_identifier
                and item.get("is_active", True)
                for item in models
            )
            rois = self._fetch_rois() if self.with_rois else []
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError) as error:
            print(f"[settings] refresh failed, keeping last known: {error}", flush=True)
            return

        if enabled != self.model_enabled:
            state = "enabled" if enabled else "disabled"
            print(f"[settings] {self.model_identifier} model {state} for this camera", flush=True)
        if self.with_rois and [roi["id"] for roi in rois] != [roi["id"] for roi in self.rois]:
            print(f"[settings] {len(rois)} ROI(s) for this camera", flush=True)
        self.model_enabled = enabled
        self.rois = rois

    def _fetch_rois(self):
        rois = []
        url = f"roi/?camera_id={self.config.camera_id}"
        while url:
            page = self._get(url)
            items = page["results"] if isinstance(page, dict) else page
            for item in items:
                rois.append({
                    "id": item["id"],
                    "name": item["name"],
                    "polygon": [_xy(point) for point in item["polygon"]],
                })
            url = page.get("next") if isinstance(page, dict) else None
        return rois

    def _get(self, path_or_url):
        url = path_or_url if "://" in path_or_url else self.api_base + path_or_url
        http_request = request.Request(
            url, headers={"Authorization": self.config.authorization}, method="GET"
        )
        with request.urlopen(http_request, timeout=self.config.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _xy(point):
    """An ROI point as (x, y). The API stores {"x": .., "y": ..}; ROIs created
    outside the API may hold plain [x, y] pairs, which are accepted too."""
    if isinstance(point, dict):
        return (point["x"], point["y"])
    x, y = point
    return (x, y)
