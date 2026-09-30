# ANPR detector service.
#
# Runs headless.py, which reads plates from a video file or RTSP stream and
# POSTs every vehicle crossing the camera's virtual line to the SFLMS backend
# as a vehicle_entry / vehicle_exit CameraEvent. It shares the protected_media
# volume with the backend because the ingestion API requires the snapshot JPEG
# to exist before it will accept the event.

# The torch + CUDA wheels are ~3 GB, the same set the fire/smoke image
# installs. On a machine that already built that image, pass
#   --build-arg BASE_IMAGE=sflms-detector:dev   (ANPR_BASE_IMAGE in compose)
# and pip finds torch already installed, so only PaddleOCR is downloaded. The
# default builds from scratch, for a machine without it.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# ffmpeg gives OpenCV its video decoders. PaddleOCR pulls in the desktop
# opencv-contrib build, which links against libGL and libglib; libgomp1 is
# PaddlePaddle's OpenMP runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Not /detector: a fire/smoke base image keeps its own files there.
WORKDIR /anpr

COPY requirements-service.txt ./

# Same defences as the fire/smoke image against a slow link: a BuildKit cache
# mount, shared with that build, so the CUDA wheels it already downloaded are
# reused and a timeout resumes rather than restarts; and generous retries.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 -r requirements-service.txt

COPY . ./

# PaddleOCR downloads its recognition model (~10 MB) on first use into
# PADDLE_PDX_CACHE_HOME; compose mounts a named volume there so it is fetched
# once, not on every container start.
ENV PYTHONUNBUFFERED=1 \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    PADDLE_PDX_CACHE_HOME=/paddlex-cache

CMD ["python", "headless.py"]
