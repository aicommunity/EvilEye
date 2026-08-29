# syntax=docker/dockerfile:1.7
ARG ULTRALYTICS_TAG=8.4.115
FROM ultralytics/ultralytics:${ULTRALYTICS_TAG}

LABEL org.opencontainers.image.title="EvilEye" \
      org.opencontainers.image.description="Intelligence video surveillance (GPU) from PyPI" \
      org.opencontainers.image.source="https://github.com/aicommunity/EvilEye"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/opt/evileye

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

COPY docker/install_pypi_deps.py /tmp/install_pypi_deps.py
COPY docker/entrypoint.sh /usr/local/bin/evileye-entrypoint
COPY docker/bootstrap_site.py /opt/evileye/docker/bootstrap_site.py
COPY docker/compose.site.gpu.yml /opt/evileye/docker/compose.site.gpu.yml
COPY docker/compose.site.cpu.yml /opt/evileye/docker/compose.site.cpu.yml
COPY docker/host-cli /opt/evileye/docker/host-cli

RUN chmod +x /tmp/install_pypi_deps.py /usr/local/bin/evileye-entrypoint /opt/evileye/docker/bootstrap_site.py \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --no-deps evileye \
    && python /tmp/install_pypi_deps.py --package evileye --skip torch,torchvision,torchaudio,ultralytics \
    && rm -f /tmp/install_pypi_deps.py \
    && python -c "import evileye, torch, ultralytics; print('evileye ok', evileye.__version__)"

EXPOSE 8181

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import evileye, torch, ultralytics" || exit 1

ENTRYPOINT ["evileye-entrypoint"]
CMD ["evileye", "server", "--host", "0.0.0.0", "--port", "8181", "--no-reload"]
