#!/usr/bin/env bash
# Publish the laptop webcam to the MediaMTX relay as an RTSP stream.
#
# This is the missing half of the containerised detector path. Docker Desktop
# on Windows cannot forward a webcam into a container, so the host publishes
# the camera as RTSP and the container consumes it:
#
#   host: webcam --ffmpeg--> rtsp://localhost:8554/laptop
#   container: detector <--rtsp://mediamtx:8554/laptop
#
# Requires the stack to be up (`docker compose up -d`) so MediaMTX is
# listening on 8554. ffmpeg comes from the imageio-ffmpeg wheel, so no
# system-wide install is needed.
#
#   ./publish_webcam.sh                        publish until Ctrl+C
#   WEBCAM_DEVICE="Other Cam" ./publish_webcam.sh
#   RTSP_PATH=frontdoor ./publish_webcam.sh
#
set -euo pipefail

DEVICE="${WEBCAM_DEVICE:-Integrated Webcam}"
RTSP_HOST="${RTSP_HOST:-localhost}"
RTSP_PORT="${RTSP_PORT:-8554}"
RTSP_PATH="${RTSP_PATH:-laptop}"
FPS="${WEBCAM_FPS:-30}"
SIZE="${WEBCAM_SIZE:-640x480}"
# This camera advertises its modes as vcodec=mjpeg at fixed frame rates -- at
# 640x480 only 30fps exists. Requesting a rate it does not list fails with
# "Could not set video options", so name the input codec explicitly.
# Check yours with:
#   ffmpeg -f dshow -list_options true -i video="<device>"
INPUT_CODEC="${WEBCAM_INPUT_CODEC:-mjpeg}"

FFMPEG="$(python -c 'import imageio_ffmpeg,sys; sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)"
if [ -z "$FFMPEG" ]; then
  FFMPEG="$(command -v ffmpeg || true)"
fi
if [ -z "$FFMPEG" ]; then
  echo "ffmpeg not found. Install it with:  pip install imageio-ffmpeg" >&2
  exit 1
fi

TARGET="rtsp://${RTSP_HOST}:${RTSP_PORT}/${RTSP_PATH}"

if ! (exec 3<>"/dev/tcp/${RTSP_HOST}/${RTSP_PORT}") 2>/dev/null; then
  echo "Nothing is listening on ${RTSP_HOST}:${RTSP_PORT}." >&2
  echo "Start the stack first:  docker compose up -d" >&2
  exit 1
fi

echo "device : $DEVICE"
echo "target : $TARGET"
echo "format : ${SIZE} @ ${FPS}fps  in=${INPUT_CODEC}  out=H.264 zerolatency"
echo

# A real camera does not stop publishing because one TCP connection dropped.
# ffmpeg exits on "Broken pipe" when MediaMTX restarts, when a container is
# recreated, or on a transient USB stall, so supervise it and reconnect.
# Ctrl+C still stops the whole thing, because the trap exits the loop.
trap 'echo; echo "stopping publisher"; exit 0' INT TERM

attempt=0
while true; do
  attempt=$((attempt + 1))
  [ "$attempt" -gt 1 ] && echo "--- reconnecting (attempt $attempt) ---"

  # -rtbufsize guards against dropped frames while the encoder warms up.
  # ultrafast/zerolatency keep glass-to-detector delay low; this is a live
  # monitoring feed, not an archive, so compression efficiency is irrelevant.
  "$FFMPEG" -hide_banner -loglevel warning \
    -f dshow -rtbufsize 128M -vcodec "$INPUT_CODEC" \
    -framerate "$FPS" -video_size "$SIZE" \
    -i "video=$DEVICE" \
    -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p \
    -g "$FPS" -b:v 1500k -an \
    -f rtsp -rtsp_transport tcp "$TARGET" || true

  # Brief pause so a hard failure (camera unplugged, MediaMTX down) does not
  # spin the CPU reconnecting hundreds of times per second.
  sleep 2
done
