# EvilEye Makefile
# Provides convenient commands for development and project management

.PHONY: install install-dev uninstall clean test lint format docs fix-entry-points \
	docker-build docker-up install-docker-cli uninstall-docker-cli prepare-docker-host

# Default target
all: install

# Install package in development mode
install:
	@echo "Installing EvilEye package..."
	pip install -e .
	@echo "Fixing entry points..."
	python scripts/setup/fix_entry_points.py
	@echo "✅ Installation complete!"

# Install with development dependencies
install-dev:
	@echo "Installing EvilEye package with development dependencies..."
	pip install -e ".[dev]"
	@echo "Fixing entry points..."
	python scripts/setup/fix_entry_points.py
	@echo "✅ Development installation complete!"

# Install with development dependencies (alias; [full] extra does not exist)
install-full: install-dev

# Uninstall package
uninstall:
	@echo "Uninstalling EvilEye package..."
	pip uninstall evileye -y
	@echo "✅ Uninstallation complete!"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "✅ Clean complete!"

# Run tests
test:
	@echo "Running tests..."
	pytest tests/ -v

# Run linting
lint:
	@echo "Running linting..."
	flake8 evileye/ tests/
	mypy evileye/

# Format code
format:
	@echo "Formatting code..."
	black evileye/ tests/
	isort evileye/ tests/

# Build documentation
docs:
	@echo "Building documentation..."
	cd docs && make html

# Fix entry points manually
fix-entry-points:
	@echo "Fixing entry points..."
	python scripts/setup/fix_entry_points.py

# Reinstall (uninstall + install)
reinstall: uninstall install

# Reinstall with development dependencies
reinstall-dev: uninstall install-dev

# Reinstall with all dependencies
reinstall-full: uninstall install-full

# --- Docker (GPU) ---
# See docs/DOCKER_DEPLOYMENT.md. Does not affect pip install targets above.

prepare-docker-host:
	./docker/prepare-host-dirs.sh

docker-build:
	docker compose -f docker/docker-compose.yml build

docker-up:
	docker compose -f docker/docker-compose.yml up

install-docker-cli:
	./docker/install-host-cli.sh

uninstall-docker-cli:
	./docker/uninstall-host-cli.sh

# Show help
help:
	@echo "Available targets:"
	@echo "  install          - Install package in development mode"
	@echo "  install-dev      - Install with development dependencies"
	@echo "  install-full     - Install with all dependencies"
	@echo "  uninstall        - Uninstall package"
	@echo "  clean            - Clean build artifacts"
	@echo "  test             - Run tests"
	@echo "  lint             - Run linting"
	@echo "  format           - Format code"
	@echo "  docs             - Build documentation"
	@echo "  fix-entry-points - Fix entry points manually"
	@echo "  reinstall        - Uninstall and install"
	@echo "  reinstall-dev    - Uninstall and install with dev deps"
	@echo "  reinstall-full   - Uninstall and install with all deps"
	@echo "  prepare-docker-host - Create host data dirs + credentials.json for Docker"
	@echo "  docker-build     - Build GPU Docker image (Ultralytics/PyTorch/CUDA)"
	@echo "  docker-up        - Run docker compose stack (app + Postgres)"
	@echo "  install-docker-cli - Install host CLI wrappers that call the container"
	@echo "  uninstall-docker-cli - Remove Docker host CLI wrappers"
	@echo "  help             - Show this help"
