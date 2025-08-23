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

#### Automatic Installation (Recommended)

```bash
# Install with all dependencies (automatically fixes entry points)
python install.py --full

# Or install specific components
python install.py --gui    # With GUI support
python install.py --gpu    # With GPU support
python install.py --dev    # With development tools
```

#### Manual Installation

```bash
# Install with all dependencies
pip install -e ".[full]"

# Fix entry points manually
./fix_entry_points.sh

# Or install specific components
pip install -e ".[gui]"    # With GUI support
pip install -e ".[gpu]"    # With GPU support
pip install -e ".[dev]"    # With development tools
```

#### Using Makefile

```bash
# Install with all dependencies
make install-full

# Install with development tools
make install-dev

# Reinstall (uninstall + install)
make reinstall
```

### Basic Usage

```bash
# Deploy configuration files to current directory
evileye deploy

# Create new configuration
evileye-create my_config --sources 2 --source-type video_file

# Run with configuration file
evileye run configs/my_config.json

# Validate configuration
evileye validate configs/my_config.json

# List available configurations
evileye list-configs

# Show system information
evileye info

# Launch GUI
evileye gui
```

### Using the GUI

```bash
# Launch the graphical interface
evileye gui
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

## CLI Commands

EvilEye provides a comprehensive command-line interface for all operations:

### Deployment and Setup

```bash
# Deploy configuration files to current directory
evileye deploy

# Creates:
# - credentials.json (from credentials_proto.json)
# - configs/ folder
```

### Configuration Management

```bash
# List available pipeline classes
evileye-create --list-pipelines

# Create new configuration file
evileye-create my_config --sources 2 --source-type video_file

# Create configuration with specific pipeline
evileye-create my_config --sources 2 --pipeline PipelineSurveillance

# Available source types:
# - video_file: Video files (.mp4, .avi, etc.)
# - ip_camera: IP cameras (RTSP streams)
# - device: USB/web cameras

# Validate configuration file
evileye validate configs/my_config.json

# List available configurations
evileye list-configs
```

### System Operations

```bash
# Run EvilEye with configuration
evileye run configs/my_config.json

# Run with specific options
evileye run configs/my_config.json --gui --autoclose

# Show system information
evileye info
```

### Complete Workflow Example

```bash
# 1. Deploy files to new project directory
mkdir my_surveillance_project
cd my_surveillance_project
evileye deploy

# 2. Create configuration for 2 IP cameras
evileye-create surveillance_config --sources 2 --source-type ip_camera

# 3. Edit credentials.json with your camera credentials
# 4. Edit configs/surveillance_config.json with your camera URLs

# 5. Validate configuration
evileye validate configs/surveillance_config.json

# 6. Run the system
evileye run configs/surveillance_config.json

# Alternative: Use specific pipeline class
evileye-create custom_config --sources 2 --pipeline PipelineSurveillance
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

### Pipeline Classes

EvilEye supports multiple pipeline implementations:

- **PipelineSurveillance** - Full-featured pipeline with all components
- **Custom Pipelines** - User-defined pipeline implementations

Pipeline classes are automatically discovered from:
- Built-in `evileye.pipelines` package
- Local `pipelines/` folder in working directory

Create custom pipelines by extending the base `Pipeline` class and placing them in a local `pipelines/` folder.

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
