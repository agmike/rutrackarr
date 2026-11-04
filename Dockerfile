# syntax=docker/dockerfile:1.7
# rutrackarr — rootless image: UI built with Node, backend in a uv-managed venv,
# runtime on python slim as a fixed non-root user (65532). Only /data is writable.

ARG PYTHON_IMAGE=python:3.13-slim

FROM node:24-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
ARG VERSION=dev
LABEL org.opencontainers.image.title="rutrackarr" \
      org.opencontainers.image.description="Torznab indexer for RuTracker with language-aware ranking for Sonarr/Radarr" \
      org.opencontainers.image.source="https://github.com/agmike/rutrackarr" \
      org.opencontainers.image.licenses="MIT"
RUN groupadd --gid 65532 nonroot \
 && useradd --uid 65532 --gid 65532 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin nonroot \
 && install -d -o 65532 -g 65532 -m 0750 /data
COPY --from=build /app/.venv /app/.venv
COPY --from=ui /ui/dist /app/static
ENV RUTRACKARR_VERSION=${VERSION} \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUTRACKARR_DATA_DIR=/data \
    RUTRACKARR_STATIC_DIR=/app/static \
    RUTRACKARR_PORT=8787
USER 65532:65532
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; b=os.environ.get('RUTRACKARR_URL_BASE','').strip().rstrip('/'); b=('/'+b.lstrip('/')) if b else ''; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ['RUTRACKARR_PORT']}{b}/api/health\", timeout=4)"]
ENTRYPOINT ["rutrackarr"]
