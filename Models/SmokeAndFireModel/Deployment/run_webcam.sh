#!/usr/bin/env bash
# Run the fire/smoke detector against the laptop webcam, treating it as a
# CCTV camera registered in SFLMS (CAM-LAPTOP-01).
#
# This runs on the HOST, not in a container: Docker Desktop on Windows cannot
# pass a webcam through to a Linux container, and the host already has a
# working CUDA torch. The backend stack must be up (`docker compose up -d`),
# because snapshots are written into ./protected_media, which the backend
# bind-mounts, and events are POSTed to the API on localhost:8000.
#
#   ./run_webcam.sh                 run until Ctrl+C
#   MAX_RUNTIME_SECONDS=60 ./run_webcam.sh    stop after a minute
#   DETECTOR_DEVICE=cpu ./run_webcam.sh       force CPU
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"

# Under Git Bash, pwd yields an MSYS path (/w/Disk E/...) that the Windows
# Python interpreter cannot open. pwd -W gives the native W:/... form. On a
# real POSIX host pwd -W does not exist, so fall back to the value above.
if REPO_WIN="$(cd "$REPO" && pwd -W 2>/dev/null)" && [ -n "$REPO_WIN" ]; then
  REPO="$REPO_WIN"
fi

# Credentials and camera identity come from the repo .env so they are not
# duplicated here. Only the webcam-specific overrides live below.
if [ -f "$REPO/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO/.env"
  set +a
fi

: "${SFLMS_KEY_ID:?SFLMS_KEY_ID missing from .env}"
: "${SFLMS_SECRET:?SFLMS_SECRET missing from .env}"

export SFLMS_API_URL="${SFLMS_API_URL_HOST:-http://localhost:8000/api/v1/camera-events/}"
export SFLMS_PROTECTED_MEDIA_ROOT="${SFLMS_PROTECTED_MEDIA_ROOT_HOST:-$REPO/protected_media}"
export SFLMS_CAMERA_ID="${WEBCAM_CAMERA_ID:?WEBCAM_CAMERA_ID missing from .env}"
export SFLMS_FACILITY_ID="${SFLMS_FACILITY_ID:?SFLMS_FACILITY_ID missing from .env}"

# 0 is the built-in webcam. VIDEO_LOOP is irrelevant for a live device: the
# stream does not "end" until the camera is released.
export VIDEO_SOURCE="${WEBCAM_INDEX:-0}"
export VIDEO_LOOP=0
export DETECTOR_DEVICE="${DETECTOR_DEVICE:-0}"
export MAX_RUNTIME_SECONDS="${MAX_RUNTIME_SECONDS:-0}"

echo "camera   : CAM-LAPTOP-01 ($SFLMS_CAMERA_ID)"
echo "source   : webcam index $VIDEO_SOURCE"
echo "api      : $SFLMS_API_URL"
echo "snapshots: $SFLMS_PROTECTED_MEDIA_ROOT"
echo

cd "$HERE"
exec python headless.py
