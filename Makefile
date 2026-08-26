# EvilEye Makefile

.PHONY: install install-dev uninstall clean test lint format docs fix-entry-points \
	docker-build docker-build-cpu docker-up docker-bootstrap-site docker-push \
	install-docker-cli uninstall-docker-cli prepare-docker-host

all: install

install:
	@echo "Installing EvilEye package..."
	pip install -e .
	python scripts/setup/fix_entry_points.py
	@echo "✅ Installation complete"

install-dev:
	@echo "Installing EvilEye package with development dependencies..."
	pip install -e ".[dev]"
	python scripts/setup/fix_entry_points.py
	@echo "✅ Development installation complete"

install-full: install-dev

uninstall:
	pip uninstall evileye -y

clean:
	rm -rf build/ dist/ *.egg-info/ __pycache__/ .pytest_cache/ .coverage htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test:
	pytest tests/ -v

lint:
	flake8 evileye/ tests/
	mypy evileye/

format:
	black evileye/ tests/
	isort evileye/ tests/

docs:
	cd docs && make html

fix-entry-points:
	python scripts/setup/fix_entry_points.py

reinstall: uninstall install
reinstall-dev: uninstall install-dev
reinstall-full: uninstall install-full

prepare-docker-host:
	./docker/prepare-host-dirs.sh

docker-build:
	docker build -f docker/Dockerfile -t evileye/app:latest .

docker-build-cpu:
	docker build -f docker/Dockerfile.cpu -t evileye/app:cpu .

docker-up:
	docker compose -f docker/docker-compose.yml up -d --build

docker-bootstrap-site:
	@echo "Usage: mkdir site && cd site && docker run --rm -v \"$$PWD\":/site evileye/app:latest bootstrap"

docker-push:
	docker push evileye/app:latest
	docker push evileye/app:cpu

install-docker-cli:
	./docker/install-host-cli.sh

uninstall-docker-cli:
	./docker/uninstall-host-cli.sh

help:
	@echo "Targets:"
	@echo "  docker-build       Build GPU image"
	@echo "  docker-build-cpu   Build CPU image"
	@echo "  docker-up          Run compose stack"
	@echo "  docker-push        Push latest and cpu tags"
