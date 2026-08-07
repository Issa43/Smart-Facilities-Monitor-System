"""Wait for PostgreSQL and Redis before starting a container process."""

import os
import sys
import time
from urllib.parse import urlparse

import psycopg2
import redis


def wait_for(name, connect, timeout, interval):
    deadline = time.monotonic() + timeout
    while True:
        try:
            resource = connect()
            resource.close()
            print(f"{name} is ready.", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 - readiness retries all connection failures
            if time.monotonic() >= deadline:
                print(f"Timed out waiting for {name}: {exc}", file=sys.stderr, flush=True)
                raise SystemExit(1) from exc
            print(f"Waiting for {name}...", flush=True)
            time.sleep(interval)


def postgres_connection():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "sflms_db"),
        user=os.getenv("DB_USER", "sflms_user"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "postgres"),
        port=os.getenv("DB_PORT", "5432"),
    )


def redis_connection():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    client = redis.Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
    client.ping()
    return client


def main():
    timeout = float(os.getenv("SERVICE_WAIT_TIMEOUT", "60"))
    interval = float(os.getenv("SERVICE_WAIT_INTERVAL", "2"))

    wait_for("PostgreSQL", postgres_connection, timeout, interval)
    wait_for("Redis", redis_connection, timeout, interval)

    redis_host = urlparse(os.getenv("REDIS_URL", "redis://redis:6379/0")).hostname
    print(f"Infrastructure dependencies are ready (Redis host: {redis_host}).", flush=True)


if __name__ == "__main__":
    main()
