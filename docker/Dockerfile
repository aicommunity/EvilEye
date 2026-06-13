# syntax=docker/dockerfile:1.7-labs

# Base: NVIDIA CUDA (Ubuntu 22.04) for GPU workloads
FROM nvidia/cuda:12.2.2-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps (Python, build tools, GStreamer, OpenCV deps, psycopg2 deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv python3-pip \
    build-essential pkg-config \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    libgstreamer1.0-0 gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-libav \
    gstreamer1.0-tools \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create app user and dirs
ARG APP_USER=appuser
ARG APP_HOME=/opt/evileye
RUN useradd -ms /bin/bash ${APP_USER} && mkdir -p ${APP_HOME}
WORKDIR ${APP_HOME}

# Copy only dependency manifests first for better layering
COPY --chown=${APP_USER}:${APP_USER} requirements.txt pyproject.toml ${APP_HOME}/

# Create venv and install deps
RUN python3 -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install --upgrade pip wheel setuptools \
    && if [ -f requirements.txt ]; then pip install -r requirements.txt; fi \
    && pip install . || true

# Copy source
COPY --chown=${APP_USER}:${APP_USER} . ${APP_HOME}/

# Reinstall project (editable-like)
RUN . /opt/venv/bin/activate && pip install -e .

# Runtime env
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=${APP_HOME}

# Create data directories (bind-mounts recommended)
RUN mkdir -p ${APP_HOME}/EvilEyeData/images ${APP_HOME}/logs ${APP_HOME}/videos
VOLUME ["${APP_HOME}/EvilEyeData", "${APP_HOME}/logs", "${APP_HOME}/videos"]

# Expose optional UI/WS ports if needed (adjust as appropriate)
EXPOSE 8501 8080

# Healthcheck: python import
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import evileye; print('ok')" || exit 1

# Default command (override in docker-compose): run CLI with a config
CMD ["python", "-m", "evileye.cli", "--config", "configs/single_video.json", "--gui", "true"]
