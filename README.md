# EvilEye

Intelligence video surveillance system with object detection, tracking, and multi-camera support.

## Features

- **Multi-camera support** - Process multiple video sources simultaneously
- **Object detection** - YOLO-based object detection with customizable models
- **Object tracking** - Advanced tracking algorithms with re-identification
- **Pipeline architecture** - Modular and extensible processing pipeline
- **GUI and CLI** - Both graphical and command-line interfaces
- **Database integration** - PostgreSQL support for event storage
- **Real-time processing** - Optimized for real-time video analysis

## Quick Start

### Installation

```bash
# Install with all dependencies
pip install -e ".[full]"

# Or install specific components
pip install -e ".[gui]"    # With GUI support
pip install -e ".[gpu]"    # With GPU support
pip install -e ".[dev]"    # With development tools
```

### Basic Usage

```bash
# Run with configuration file
evileye run configs/single_cam.json

# Validate configuration
evileye validate configs/single_cam.json

# List available configurations
evileye list-configs

# Show system information
evileye info

# Launch GUI
evileye-gui
```

### Using the GUI

```bash
# Launch the graphical interface
evileye-gui
```

The GUI provides:
- Configuration file browser
- Real-time pipeline control
- Configuration editor and validation
- Live logs and status monitoring

## Configuration

EvilEye uses JSON configuration files. Example configuration:

```json
{
  "pipeline": {
    "sources": [
      {
        "source": "IpCamera",
        "camera": "rtsp://camera-ip:554/stream",
        "source_ids": [0],
        "source_names": ["Main Camera"]
      }
    ],
    "detectors": [
      {
        "source_ids": [0],
        "model": "yolov8n.pt",
        "conf": 0.4,
        "classes": [0, 1, 24, 25]
      }
    ],
    "trackers": [
      {
        "source_ids": [0],
        "fps": 30,
        "tracker_type": "botsort"
      }
    ],
    "mc_trackers": [
      {
        "source_ids": [0],
        "enable": true
      }
    ]
  },
  "controller": {
    "fps": 30,
    "show_main_gui": true
  }
}
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/evileye/evileye.git
cd evileye

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows

# Install development dependencies
make install-dev

# Setup pre-commit hooks
make dev-setup
```

### Development Commands

```bash
# Run tests
make test

# Run tests with coverage
make test-cov

# Format code
make format

# Lint code
make lint

# Type checking
make type-check

# Full quality check
make quality

# Build package
make build

# Clean build artifacts
make clean
```

### Project Structure

```
evileye/
├── core/                    # Core pipeline components
│   ├── pipeline.py         # Base pipeline class
│   ├── processor_base.py   # Base processor class
│   └── ...
├── pipelines/              # Pipeline implementations
│   └── pipeline_surveillance.py
├── object_detector/        # Object detection modules
├── object_tracker/         # Object tracking modules
├── object_multi_camera_tracker/  # Multi-camera tracking
├── events_detectors/       # Event detection
├── database_controller/    # Database integration
├── visualization_modules/  # GUI components
├── configs/               # Configuration files
├── tests/                 # Test suite
├── evileye/               # Package entry points
│   ├── cli.py            # Command-line interface
│   ├── gui.py            # Graphical interface
│   └── __init__.py       # Package initialization
├── pyproject.toml        # Project configuration
├── Makefile              # Development commands
└── README.md             # This file
```

## Architecture

EvilEye uses a modular pipeline architecture:

1. **Sources** - Video capture from cameras, files, or streams
2. **Preprocessors** - Frame preprocessing and enhancement
3. **Detectors** - Object detection using YOLO models
4. **Trackers** - Object tracking and trajectory analysis
5. **Multi-camera Trackers** - Cross-camera object re-identification

Each component is implemented as a processor that can be configured and combined to create custom surveillance pipelines.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Use type hints
- Write docstrings for all functions and classes
- Run `make quality` before submitting PRs

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [https://evileye.readthedocs.io/](https://evileye.readthedocs.io/)
- **Issues**: [https://github.com/evileye/evileye/issues](https://github.com/evileye/evileye/issues)
- **Discussions**: [https://github.com/evileye/evileye/discussions](https://github.com/evileye/evileye/discussions)

## Acknowledgments

- [Ultralytics](https://github.com/ultralytics/ultralytics) for YOLO models
- [OpenCV](https://opencv.org/) for computer vision
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) for GUI
