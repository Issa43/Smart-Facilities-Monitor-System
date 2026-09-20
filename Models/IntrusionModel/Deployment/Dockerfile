# Intrusion detector service.
#
# Runs headless.py, which watches a video file or RTSP stream for people entering
# the intrusion zone and POSTs each confirmation to the SFLMS backend as a
# CameraEvent. It shares the protected_media volume with the backend because
# the ingestion API requires the snapshot JPEG to exist before accepting the event.

FROM python:3.12-slim

# ffmpeg gives OpenCV its video decoders; libglib2.0-0 is the one shared
# library opencv-python-headless still links against.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /detector

COPY requirements.txt ./

# The CUDA wheels are ~3 GB and come partly from pypi.nvidia.com, which times
# out on a slow link (the frontend image needs the same treatment for npm).
# Two defences:
#   - a BuildKit cache mount, so a timeout does not discard everything already
#     downloaded; re-running the build resumes instead of starting over
#   - generous per-read timeout and retry count
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 -r requirements.txt

COPY . ./

ENV PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics

# Fail fast and loudly rather than idling if the stream or credentials are wrong.
CMD ["python", "headless.py"]
