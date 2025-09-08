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

#### From PyPI (Users)

```bash
# Install from PyPI with all dependencies
pip install evileye

```

#### From Source (Developers)

```bash
# Clone the repository
git clone https://github.com/evileye/evileye.git
cd EvilEye

# Install in development mode
pip install -e "."

# Fix entry points
python fix_entry_points.py

Next you can use the 'evileye' command to work, or if the command does not work:
python3 -m evileye.cli_wrapper
```

### Basic Usage

EvilEye provides multiple entry points for different use cases:

```bash
# Deploy sample configurations (recommended for beginners)
evileye deploy-samples

# Deploy EvilEye system to current directory
evileye deploy

# List available configurations
evileye list-configs

# Run with configuration ('configs/' prefix may be omitted)
evileye run configs/my_config.json

# Create new configuration
evileye-create my_config --sources 2 --source-type video_file

# Launch main application with GUI
evileye-launch

# Open configuration editor
evileye-configure configs/my_config.json

# Direct process launcher
evileye-process --config configs/my_config.json
```

**Quick Start Options:**
- **GUI Users**: Use `evileye-launch` for the main application interface
- **CLI Users**: Use `evileye` commands for command-line operations
- **Configuration**: Use `evileye-configure` for visual configuration editing
- **Automation**: Use `evileye-process` for headless operation

#### After Running `evileye deploy`

The `deploy` command creates the following structure in your current directory:

```
your_project/
├── credentials.json          # Database and camera credentials
└── configs/                  # Configuration files directory
    └── (empty - ready for your configs)
```

#### After Running `evileye deploy-samples`

The `deploy-samples` command creates the following structure in your current directory:

```
your_project/
├── credentials.json          # Database and camera credentials
├── videos/                   # Sample video files
│   ├── planes_sample.mp4     # Single video with planes
│   ├── sample_split.mp4      # Video with two camera views
│   ├── 6p-c0.avi            # Multi-camera tracking (camera 0)
│   └── 6p-c1.avi            # Multi-camera tracking (camera 1)
└── configs/                  # Configuration files directory
    ├── single_video.json     # Single video processing
    ├── single_video_split.json # Video with 2-way split
    ├── multi_videos.json     # Multiple videos with tracking
    ├── single_ip_camera.json # IP camera processing
    └── README_SAMPLES.md     # Sample configurations guide
```

#### Credentials Configuration

The `credentials.json` file contains database and camera access credentials:

```json
{
  "sources": {
    "rtsp://camera1.example.com": {
      "username": "camera_user",
      "password": "camera_password"
    },
    "rtsp://camera2.example.com": {
      "username": "admin",
      "password": "admin123"
    }
  },
  "database": {
    "user_name": "postgres",
    "password": "your_db_password",
    "database_name": "evil_eye_db",
    "host_name": "localhost",
    "port": 5432,
    "default_database_name": "postgres",
    "default_password": "your_default_password",
    "default_user_name": "postgres",
    "default_host_name": "localhost",
    "default_port": 5432
  }
}
```

⚠️ **Security Warning**: The `credentials.json` file contains plain text passwords. Store this file securely and never commit it to version control. Consider using environment variables or a secure credential manager for production deployments.



## Configuration

EvilEye uses JSON configuration files for the **PipelineSurveillance** class. The configuration is divided into sections that define different components of the surveillance pipeline.

⚠️ **Important**: The configuration structure described above is specific to the **PipelineSurveillance** class. Other pipeline classes may have different configuration requirements and structure.

### Configuration Structure

```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [...],      // Video sources configuration
    "detectors": [...],    // Object detection configuration
    "trackers": [...],     // Object tracking configuration
    "mc_trackers": [...]   // Multi-camera tracking configuration
  },
  "controller": {
    "fps": 30,
    "show_main_gui": true
  }
}
```

### Sources Configuration

The `sources` section defines video input sources. Each source can be configured with different types and splitting options.

#### Source Types

**1. IP Camera (`IpCamera`)**
```json
{
  "source": "IpCamera",
  "camera": "rtsp://url",
  "apiPreference": "CAP_FFMPEG",
  "source_ids": [0],
  "source_names": ["Main Camera"]
}
```

**2. Video File (`VideoFile`)**
```json
{
  "source": "VideoFile",
  "camera": "/path/to/video.mp4",
  "apiPreference": "CAP_FFMPEG",
  "loop_play": true,
  "source_ids": [0],
  "source_names": ["Video Source"]
}
```

**3. Device Camera (`Device`)**
```json
{
  "source": "Device",
  "camera": 0,
  "apiPreference": "CAP_FFMPEG",
  "source_ids": [0],
  "source_names": ["USB Camera"]
}
```

#### Source Splitting Options

**Without Splitting (Single Output)**
```json
{
  "source": "IpCamera",
  "camera": "rtsp://url1",
  "split": false,
  "num_split": 0,
  "src_coords": [0],
  "source_ids": [0],
  "source_names": ["Camera1"]
}
```

**With Splitting (Multiple Outputs)**
```json
{
  "source": "IpCamera",
  "camera": "rtsp://url2",
  "split": true,
  "num_split": 2,
  "src_coords": [
    [0, 0, 2304, 1300],      // Top region: x, y, width, height
    [0, 1300, 2304, 1292]    // Bottom region: x, y, width, height
  ],
  "source_ids": [1, 2],
  "source_names": ["Camera2_Top", "Camera2_Bottom"]
}
```

#### Source Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `source` | string | Source type: `IpCamera`, `VideoFile`, `Device` | - |
| `camera` | string/int | Camera URL, file path, or device index | - |
| `apiPreference` | string | OpenCV API preference | `CAP_FFMPEG` |
| `split` | boolean | Enable source splitting | `false` |
| `num_split` | int | Number of split regions | `0` |
| `src_coords` | array | Coordinates for split regions | `[0]` |
| `source_ids` | array | Unique IDs for each output | - |
| `source_names` | array | Names for each output | - |
| `loop_play` | boolean | Loop video files | `true` |
| `desired_fps` | int | Target FPS for the source | `null` |

### Detectors Configuration

The `detectors` section configures object detection for each source.

#### YOLO Detector Configuration

```json
{
  "source_ids": [0],
  "model": "models/yolov8n.pt",
  "show": false,
  "inference_size": 640,
  "device": null,
  "conf": 0.4,
  "save": false,
  "stride_type": "frames",
  "vid_stride": 1,
  "classes": [0, 1, 24, 25, 63, 66, 67],
  "roi": [
    [[1790, 0, 500, 400], [1700, 0, 1000, 1045]]
  ]
}
```

#### Detector Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `source_ids` | array | Source IDs to process | - |
| `model` | string | YOLO model path | `models/yolov8n.pt` |
| `show` | boolean | Show detection results | `false` |
| `inference_size` | int | Model input size | `640` |
| `device` | string | Device for inference (`cpu`, `cuda:0`) | `null` |
| `conf` | float | Confidence threshold | `0.25` |
| `save` | boolean | Save detection results | `false` |
| `stride_type` | string | Stride type: `frames` | `frames` |
| `vid_stride` | int | Video stride | `1` |
| `classes` | array | Object classes to detect | `[0, 1, 24, 25, 63, 66, 67]` |
| `roi` | array | Regions of interest | `[[]]` |

### Trackers Configuration

The `trackers` section configures object tracking for each source.

#### Botsort Tracker Configuration

```json
{
  "source_ids": [0],
  "fps": 30,
  "tracker_type": "botsort",
  "botsort_cfg": {
    "appearance_thresh": 0.25,
    "gmc_method": "sparseOptFlow",
    "match_thresh": 0.8,
    "new_track_thresh": 0.6,
    "proximity_thresh": 0.5,
    "track_buffer": 30,
    "track_high_thresh": 0.5,
    "track_low_thresh": 0.1,
    "with_reid": false
  }
}
```

#### Tracker Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `source_ids` | array | Source IDs to track | - |
| `fps` | int | Tracking FPS | `5` |
| `tracker_type` | string | Tracker type | `botsort` |
| `botsort_cfg` | object | Botsort configuration | See above |

### Multi-Camera Trackers Configuration

The `mc_trackers` section configures cross-camera object tracking.

#### Multi-Camera Tracking Configuration

```json
{
  "source_ids": [0, 1, 2],
  "enable": true
}
```

#### Multi-Camera Tracker Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `source_ids` | array | Source IDs for cross-camera tracking | - |
| `enable` | boolean | Enable multi-camera tracking | `false` |

### Complete Configuration Examples

#### IP Camera Configuration (poly-cameras.json)

```json
{
  "pipeline": {
    "sources": [
      {
        "source": "IpCamera",
        "camera": "rtsp://url1",
        "apiPreference": "CAP_FFMPEG",
        "split": false,
        "num_split": 0,
        "src_coords": [0],
        "source_ids": [0],
        "source_names": ["Cam1"]
      },
      {
        "source": "IpCamera",
        "camera": "rtsp://url2",
        "apiPreference": "CAP_FFMPEG",
        "split": true,
        "num_split": 2,
        "src_coords": [
          [0, 0, 2304, 1300],
          [0, 1300, 2304, 1292]
        ],
        "source_ids": [1, 2],
        "source_names": ["Cam2", "Cam3"]
      }
    ],
    "detectors": [
      {
        "source_ids": [0],
        "model": "models/yolov8n.pt",
        "show": false,
        "inference_size": 640,
        "device": null,
        "conf": 0.4,
        "save": false,
        "stride_type": "frames",
        "vid_stride": 1,
        "classes": [0, 1, 24, 25, 63, 66, 67]
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
        "source_ids": [0, 1, 2],
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

#### Video File Configuration (poly-videos.json)

```json
{
  "pipeline": {
    "sources": [
      {
        "source": "VideoFile",
        "camera": "/path/to/video1.mp4",
        "apiPreference": "CAP_FFMPEG",
        "split": false,
        "num_split": 0,
        "src_coords": [0],
        "source_ids": [0],
        "source_names": ["Video1"]
      },
      {
        "source": "VideoFile",
        "camera": "/path/to/video2.mp4",
        "apiPreference": "CAP_FFMPEG",
        "split": true,
        "num_split": 2,
        "src_coords": [
          [0, 0, 2304, 1300],
          [0, 1300, 2304, 1292]
        ],
        "source_ids": [1, 2],
        "source_names": ["Video2_1", "Video2_2"]
      }
    ],
    "detectors": [
      {
        "source_ids": [0],
        "model": "models/yolov8n.pt",
        "show": false,
        "inference_size": 640,
        "device": null,
        "conf": 0.4,
        "save": false,
        "stride_type": "frames",
        "vid_stride": 1,
        "classes": [0, 1, 24, 25, 63, 66, 67]
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
        "source_ids": [0, 1, 2],
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

EvilEye provides a comprehensive command-line interface for all operations through multiple entry points:

### Available Entry Points

EvilEye provides several command-line entry points for different operations:

| Command | Description | Usage |
|---------|-------------|-------|
| `evileye` | Main CLI interface with all commands | `evileye [COMMAND] [OPTIONS]` |
| `evileye-process` | Direct process launcher with GUI | `evileye-process [OPTIONS]` |
| `evileye-configure` | Configuration editor GUI | `evileye-configure [CONFIG_FILE]` |
| `evileye-launch` | Main application launcher GUI | `evileye-launch [CONFIG_FILE]` |
| `evileye-create` | Configuration file creator | `evileye-create [NAME] [OPTIONS]` |

### Main CLI Commands (`evileye`)

The main `evileye` command provides access to all system functionality:

```bash
# Deploy configuration files to current directory
evileye deploy

# Deploy sample configurations with working examples
evileye deploy-samples

# Create new configuration
evileye-create my_config --sources 2 --source-type video_file

# Run with configuration
evileye run configs/my_config.json

# Validate configuration file
evileye validate configs/my_config.json

# List available configurations
evileye list-configs

# Show system information
evileye info
```

### Process Launcher (`evileye-process`)

Direct launcher for the surveillance process with GUI support:

```bash
# Launch with configuration file
evileye-process --config configs/my_config.json

# Launch with GUI disabled (headless mode)
evileye-process --config configs/my_config.json --no-gui

# Launch with auto-close when video ends
evileye-process --config configs/my_config.json --autoclose

# Use preset for multiple video sources
evileye-process --sources_preset multi_camera
```

**Options:**
- `--config CONFIG_FILE` - Configuration file path
- `--gui` / `--no-gui` - Enable/disable GUI (default: enabled)
- `--autoclose` - Auto-close when video ends
- `--sources_preset PRESET` - Use preset for multiple sources

### Configuration Editor (`evileye-configure`)

Graphical configuration editor for creating and modifying configuration files:

```bash
# Open configuration editor
evileye-configure

# Open specific configuration file
evileye-configure configs/my_config.json

# Open configuration from any path
evileye-configure /path/to/config.json
```

**Features:**
- Visual configuration editor
- Real-time validation
- Template-based configuration creation
- Source, detector, and tracker configuration
- Multi-camera setup support

### Application Launcher (`evileye-launch`)

Main application launcher with integrated configuration management:

```bash
# Launch main application
evileye-launch

# Launch with specific configuration
evileye-launch configs/my_config.json
```

**Features:**
- Configuration file browser
- Process control (start/stop surveillance)
- Real-time status monitoring
- Log display and management
- Tabbed interface for different functions

### Configuration Creator (`evileye-create`)

Command-line tool for creating new configuration files:

```bash
# Create basic configuration
evileye-create my_config

# Create configuration with specific number of sources
evileye-create my_config --sources 3

# Create configuration with specific source type
evileye-create my_config --sources 2 --source-type ip_camera

# Create configuration with specific pipeline
evileye-create my_config --pipeline PipelineSurveillance

# List available pipeline classes
evileye-create --list-pipelines

# Create configuration in specific directory
evileye-create /path/to/custom_config
```

**Options:**
- `--sources N` - Number of video sources (default: 0)
- `--source-type TYPE` - Source type: `video_file`, `ip_camera`, `device`
- `--pipeline PIPELINE` - Pipeline class to use
- `--list-pipelines` - List available pipeline classes

The Configuration GUI provides:
- Configuration file browser and editor
- Process control (launch/stop surveillance system via process.py)
- Real-time status monitoring
- Log display and management
- Tabbed interface for configuration, logs, and controls

### Deployment Command Details

The `evileye deploy` command:

1. **Copies** `credentials_proto.json` to `credentials.json` (if `credentials.json` doesn't exist)
2. **Creates** `configs/` folder (if it doesn't exist)
3. **Prepares** your project directory for EvilEye configuration

**Created Files:**
- `credentials.json` - Database and camera access credentials
- `configs/` - Directory for your configuration files

**Next Steps After Deploy:**
1. Edit `credentials.json` with your actual credentials
2. Create configurations using `evileye-create`
3. Run the system with `evileye run`

### Configuration Management

```bash
# List available pipeline classes
evileye-create --list-pipelines

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

### Complete Workflow Example

```bash
# 1. Deploy files to new project directory
mkdir my_surveillance_project
cd my_surveillance_project
evileye deploy

# 2. Edit credentials.json with your actual credentials
#    - Add camera usernames/passwords
#    - Configure database connection

# 3. Create configuration for 2 IP cameras
evileye-create surveillance_config --sources 2 --source-type ip_camera

# 4. Edit configs/surveillance_config.json with your camera URLs
#    - Replace "rtsp://url" with actual camera URLs
#    - Configure detection and tracking parameters

# 5. Validate configuration
evileye validate configs/surveillance_config.json

# 6. Run the system (multiple options available)
evileye run configs/surveillance_config.json

# Alternative: Use direct process launcher
evileye-process --config configs/surveillance_config.json

# Alternative: Use GUI launcher for easier management
evileye-launch

# Alternative: Use configuration editor for fine-tuning
evileye-configure configs/surveillance_config.json
```

### Entry Point Usage Scenarios

**For Beginners:**
```bash
# Use the main launcher with GUI
evileye-launch
```

**For Advanced Users:**
```bash
# Use direct process launcher with specific options
evileye-process --config configs/my_config.json --no-gui --autoclose
```

**For Configuration Management:**
```bash
# Create new configurations
evileye-create my_config --sources 3 --source-type ip_camera

# Edit existing configurations
evileye-configure configs/my_config.json

# Validate configurations
evileye validate configs/my_config.json
```

**For Automation/Scripts:**
```bash
# Use main CLI for scripting
evileye run configs/automated_config.json

# Use process launcher for headless operation
evileye-process --config configs/headless_config.json --no-gui
```

## Development

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
├── visualization_modules/  # Main application GUI components
├── configs/               # Configuration files
├── tests/                 # Test suite
├── evileye/               # Package entry points
│   ├── cli.py            # Command-line interface
│   ├── launch.py         # Configuration GUI launcher
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

- **PipelineSurveillance** - Full-featured pipeline with all components (sources, detectors, trackers, mc_trackers)
- **Custom Pipelines** - User-defined pipeline implementations

Pipeline classes are automatically discovered from:
- Built-in `evileye.pipelines` package
- Local `pipelines/` folder in working directory

#### Available Pipeline Classes

```bash
# List available pipeline classes
evileye-create --list-pipelines
```

#### Creating Custom Pipelines

Create custom pipelines by extending the base `Pipeline` class and placing them in a local `pipelines/` folder:

```python
from evileye.core.pipeline_processors import Pipeline


class MyCustomPipeline(Pipeline):
    def __init__(self):
        super().__init__()
        # Custom initialization

    def generate_default_structure(self, num_sources: int):
        # Custom configuration generation
        pass
```

Each pipeline class can define its own configuration structure and processing logic.

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
