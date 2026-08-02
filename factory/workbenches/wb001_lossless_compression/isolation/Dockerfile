FROM python:3.13.13-slim-bookworm

COPY requirements.docker.lock /tmp/requirements.docker.lock
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.docker.lock \
    && rm /tmp/requirements.docker.lock

ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR=/tmp

WORKDIR /candidate
