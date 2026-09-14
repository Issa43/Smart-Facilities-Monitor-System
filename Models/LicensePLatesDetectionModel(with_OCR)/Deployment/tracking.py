from collections import deque

import config


class TrackState:
    def __init__(self):
        self.history = deque(maxlen=config.HISTORY_SIZE)  # [(text, avg_conf), ...]
        self.box = None
        self.last_seen_frame = 0
        self.plate_type = ""
        self.stable_text = None
        self.stable_votes = 0
        self.det_conf = 0.0

        # ---- direction tracking ----
        self.current_side = None
        self.pending_side = None
        self.pending_count = 0
        self.direction = None
        self.crossing_logged = False

        # ---- vehicle type ----
        self.vehicle_type_history = deque(maxlen=10)
        self.vehicle_type = None


tracks = {}


def cleanup_stale_tracks(current_frame):
    stale_ids = [
        tid for tid, st in tracks.items()
        if current_frame - st.last_seen_frame > config.TRACK_TIMEOUT_FRAMES
    ]
    for tid in stale_ids:
        del tracks[tid]
