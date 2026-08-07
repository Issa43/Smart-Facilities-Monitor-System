FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system sflms \
    && useradd --system --gid sflms --home-dir /app sflms

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY --chown=sflms:sflms . /app
RUN mkdir -p /app/media /app/protected_media /app/staticfiles /var/lib/celery \
    && chown -R sflms:sflms /app/media /app/protected_media /app/staticfiles /var/lib/celery

USER sflms

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/docker/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
