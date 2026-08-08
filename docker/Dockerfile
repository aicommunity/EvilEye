# syntax=docker/dockerfile:1.7
#
# EvilEye GPU image on top of the official Ultralytics stack
# (PyTorch + CUDA + ultralytics / YOLO).
#
# To bump the base image, change ULTRALYTICS_TAG (or pass --build-arg).
# Check tags: https://hub.docker.com/r/ultralytics/ultralytics/tags
# Prefer a pinned semver (e.g. 8.4.115), not floating "latest".

ARG ULTRALYTICS_TAG=8.4.115
FROM ultralytics/ultralytics:${ULTRALYTICS_TAG}

LABEL org.opencontainers.image.title="EvilEye" \
      org.opencontainers.image.description="Intelligence video surveillance (GPU) on Ultralytics/PyTorch/CUDA" \
      org.opencontainers.image.source="https://github.com/aicommunity/EvilEye"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/opt/evileye \
    EVILEYE_DATA_DIR=/opt/evileye/EvilEyeData

# System deps for PostgreSQL client stack, GStreamer capture, TurboJPEG
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    libturbojpeg0 \
    libjpeg-turbo8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR ${APP_HOME}

# Manifests + package sources (see root .dockerignore)
COPY pyproject.toml README.md ./
COPY evileye ./evileye
COPY docker/install_python_deps.py /tmp/install_python_deps.py

# Install project deps without replacing CUDA torch / ultralytics from the base image,
# then install the EvilEye package itself with --no-deps.
RUN python /tmp/install_python_deps.py \
    && pip install --no-cache-dir --no-deps . \
    && rm -f /tmp/install_python_deps.py \
    && python -c "import torch, ultralytics, evileye; print('torch', torch.__version__, 'cuda_build', torch.version.cuda); print('ultralytics', ultralytics.__version__); print('evileye ok')"

RUN mkdir -p ${APP_HOME}/EvilEyeData/images \
    ${APP_HOME}/logs \
    ${APP_HOME}/videos \
    ${APP_HOME}/models \
    ${APP_HOME}/configs

EXPOSE 8181

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import evileye, torch, ultralytics" || exit 1

# Headless by default; override in compose / docker run
CMD ["evileye", "run", "configs/single_video.json", "--no-gui"]
