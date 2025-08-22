# EvilEye Makefile
# Provides convenient commands for development and project management

.PHONY: install install-dev uninstall clean test lint format docs fix-entry-points

# Default target
all: install

# Install package in development mode
install:
	@echo "Installing EvilEye package..."
	pip install -e .
	@echo "Fixing entry points..."
	./fix_entry_points.sh
	@echo "✅ Installation complete!"

# Install with development dependencies
install-dev:
	@echo "Installing EvilEye package with development dependencies..."
	pip install -e ".[dev]"
	@echo "Fixing entry points..."
	./fix_entry_points.sh
	@echo "✅ Development installation complete!"

# Install with all dependencies
install-full:
	@echo "Installing EvilEye package with all dependencies..."
	pip install -e ".[full]"
	@echo "Fixing entry points..."
	./fix_entry_points.sh
	@echo "✅ Full installation complete!"

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
	./fix_entry_points.sh

# Reinstall (uninstall + install)
reinstall: uninstall install

# Reinstall with development dependencies
reinstall-dev: uninstall install-dev

# Reinstall with all dependencies
reinstall-full: uninstall install-full

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
	@echo "  help             - Show this help"
