#!/bin/sh
set -eu

if [ "${WAIT_FOR_SERVICES:-1}" = "1" ]; then
    python /app/docker/wait_for_services.py
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-0}" = "1" ]; then
    python manage.py collectstatic --noinput --clear
fi

exec "$@"
