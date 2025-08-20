# EvilEye Makefile
# Provides convenient commands for development and project management

.PHONY: help install install-dev install-gui install-gpu install-full clean test test-cov lint format type-check docs build dist publish

# Default target
help:
	@echo "EvilEye - Intelligence Video Surveillance System"
	@echo ""
	@echo "Available commands:"
	@echo "  install      - Install the package in development mode"
	@echo "  install-dev  - Install with development dependencies"
	@echo "  install-gui  - Install with GUI dependencies"
	@echo "  install-gpu  - Install with GPU support"
	@echo "  install-full - Install with all dependencies"
	@echo "  clean        - Clean build artifacts"
	@echo "  test         - Run tests"
	@echo "  test-cov     - Run tests with coverage"
	@echo "  lint         - Run linting checks"
	@echo "  format       - Format code with black and isort"
	@echo "  type-check   - Run type checking with mypy"
	@echo "  docs         - Build documentation"
	@echo "  build        - Build package"
	@echo "  dist         - Create distribution"
	@echo "  publish      - Publish to PyPI"

# Installation targets
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-gui:
	pip install -e ".[gui]"

install-gpu:
	pip install -e ".[gpu]"

install-full:
	pip install -e ".[full]"

# Development targets
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=evileye --cov-report=html --cov-report=term-missing

lint:
	flake8 evileye/ tests/
	bandit -r evileye/

format:
	black evileye/ tests/
	isort evileye/ tests/

type-check:
	mypy evileye/

# Documentation targets
docs:
	cd docs && make html

# Build targets
build:
	python -m build

dist: build
	@echo "Distribution created in dist/"

publish: dist
	twine upload dist/*

# Development workflow
dev-setup: install-dev
	pre-commit install

# Quick development commands
run:
	python -m evileye.cli run configs/single_cam.json

run-gui:
	python -m evileye.gui

validate:
	python -m evileye.cli validate configs/single_cam.json

list-configs:
	python -m evileye.cli list-configs

info:
	python -m evileye.cli info

# Docker targets (if needed)
docker-build:
	docker build -t evileye .

docker-run:
	docker run -it --rm evileye

# Environment setup
venv:
	python -m venv .venv
	@echo "Virtual environment created. Activate with:"
	@echo "  source .venv/bin/activate  # Linux/Mac"
	@echo "  .venv\\Scripts\\activate     # Windows"

# Security checks
security:
	safety check
	bandit -r evileye/

# Performance profiling
profile:
	python -m cProfile -o profile.stats -m evileye.cli run configs/single_cam.json

# Code quality
quality: format lint type-check test

# Full development cycle
dev-cycle: clean install-dev quality test-cov

# Release preparation
release-prep: clean quality test-cov docs build
	@echo "Release preparation complete. Check dist/ for packages."
