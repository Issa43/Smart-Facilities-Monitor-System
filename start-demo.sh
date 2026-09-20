#!/usr/bin/env bash
# Start the whole SFLMS demo: containers + the webcam detector.
#
# Why the detector is not just another compose service:
# Docker Desktop on Windows cannot pass a USB/integrated webcam into a Linux
# container -- there is no /dev/video0 to forward. So the process that owns the
# camera has to run on the host. It still behaves like a CCTV camera: it
# publishes MJPEG on :8090 and POSTs events to the containerised API.
#
#   ./start-demo.sh            containers + detector (Ctrl+C stops the detector)
#   ./start-demo.sh --no-cam   containers only
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

echo "==> starting containers"
docker compose up -d

echo "==> waiting for the backend to report healthy"
until curl -sf --max-time 3 http://localhost:8000/health/ >/dev/null 2>&1; do
  sleep 2
done
echo "    backend ready"

cat <<'INFO'

  dashboard : http://localhost:8080
  api docs  : http://localhost:8000/api/docs/
  mail      : http://localhost:8025

  admin     : admin@sflms.local   / Admin@SFLMS2026!
  officer   : officer@sflms.local / Officer@SFLMS2026!

INFO

if [ "${1:-}" = "--no-cam" ]; then
  echo "==> skipping the camera detector (--no-cam)"
  exit 0
fi

echo "==> starting the webcam detector (Ctrl+C to stop)"
echo "    live view: http://localhost:8080/security/cameras"
echo
exec "$REPO/Models/SmokeAndFireModel/Deployment/run_webcam.sh"
