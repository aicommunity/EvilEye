# EvilEye Makefile

VERSION ?= $(shell python3 -c "import re; print(re.search(r'^version\s*=\s*\"([^\"]+)\"', open('pyproject.toml', encoding='utf-8').read(), re.M).group(1))")
EVILEYE_IMAGE_GPU ?= evileye/app
EVILEYE_IMAGE_CPU ?= evileye/app

.PHONY: install install-dev uninstall clean test test-unit test-integration lint format docs \
	docker-build docker-build-cpu docker-up docker-bootstrap-site docker-push \
	install-docker-cli uninstall-docker-cli prepare-docker-host

all: install

install:
	@echo "Installing EvilEye package..."
	pip install -e .
	@echo "✅ Installation complete"

install-dev:
	@echo "Installing EvilEye package with development dependencies..."
	pip install -e ".[dev]"
	@echo "✅ Development installation complete"

install-full: install-dev

uninstall:
	pip uninstall evileye -y

clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/ .pytest_cache/ .coverage htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Audit 2026-11 (TD-AUD-013): `make test` used to run the full suite
# (integration + GUI) while CI runs unit only - developer and CI checked
# different things. Aligned with CI; integration is a separate opt-in target.
test: test-unit

test-unit:
	pytest tests/unit -p no:cacheprovider -n auto -q

test-integration:
	pytest tests/integration -p no:cacheprovider -n auto -q

lint:
	python scripts/check_undefined_names.py
	python scripts/check_mypy_ratchet.py

format:
	black evileye/ tests/
	isort evileye/ tests/

docs:
	cd docs && make html

reinstall: uninstall install
reinstall-dev: uninstall install-dev
reinstall-full: uninstall install-full

prepare-docker-host:
	./docker/prepare-host-dirs.sh

docker-build:
	docker build -f docker/Dockerfile \
		--build-arg EVILEYE_VERSION=$(VERSION) \
		-t $(EVILEYE_IMAGE_GPU):$(VERSION) \
		-t $(EVILEYE_IMAGE_GPU):latest \
		.

docker-build-cpu:
	docker build -f docker/Dockerfile.cpu \
		--build-arg EVILEYE_VERSION=$(VERSION) \
		-t $(EVILEYE_IMAGE_CPU):$(VERSION)-cpu \
		-t $(EVILEYE_IMAGE_CPU):cpu \
		.

docker-up:
	EVILEYE_SITE_DIR="$(CURDIR)" EVILEYE_PG_DATA="$(CURDIR)/postgres_data" \
		docker compose --project-directory "$(CURDIR)" -f docker/docker-compose.yml up -d --build

docker-bootstrap-site:
	@SITE_DIR="$${SITE_DIR:-.}"; \
	IMAGE="$${EVILEYE_IMAGE:-evileye/app:latest}"; \
	mkdir -p "$$SITE_DIR"; \
	ABS="$$(cd "$$SITE_DIR" && pwd)"; \
	docker run --rm -v "$$ABS":/site \
		-e EVILEYE_BOOTSTRAP_IMAGE="$$IMAGE" \
		-e EVILEYE_BOOTSTRAP_FORCE="$${EVILEYE_BOOTSTRAP_FORCE:-}" \
		-e POSTGRES_PASSWORD="$${POSTGRES_PASSWORD:-}" \
		"$$IMAGE" bootstrap $${EVILEYE_BOOTSTRAP_FORCE:+--force}

docker-push:
	docker push $(EVILEYE_IMAGE_GPU):$(VERSION)
	docker push $(EVILEYE_IMAGE_GPU):latest
	docker push $(EVILEYE_IMAGE_CPU):$(VERSION)-cpu
	docker push $(EVILEYE_IMAGE_CPU):cpu

install-docker-cli:
	./docker/install-host-cli.sh

uninstall-docker-cli:
	./docker/uninstall-host-cli.sh

help:
	@echo "Targets:"
	@echo "  docker-build           Build GPU image (tags :$(VERSION) and :latest)"
	@echo "  docker-build-cpu       Build CPU image (tags :$(VERSION)-cpu and :cpu)"
	@echo "  docker-up              Run compose stack from repo root"
	@echo "  docker-bootstrap-site  Bootstrap SITE_DIR=. with Hub image"
	@echo "  docker-push            Push version + latest/cpu tags"
