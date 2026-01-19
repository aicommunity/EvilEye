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
git clone https://github.com/aicommunity/EvilEye.git
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
evileye create my_config --sources 2 --source-type video_file

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
    ├── single_video_rtdetr.json # Single video with RT-DETR detector
    ├── multi_videos_rtdetr.json # Multiple videos with RT-DETR detector
    ├── single_video_rfdetr.json # Single video with RF-DETR detector
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

**Security Warning**: The `credentials.json` file contains plain text passwords. Store this file securely and never commit it to version control. Consider using environment variables or a secure credential manager for production deployments.



## Configuration

EvilEye uses JSON configuration files for the **PipelineSurveillance** class. The configuration is divided into sections that define different components of the surveillance pipeline.

**Important**: The configuration structure described above is specific to the **PipelineSurveillance** class. Other pipeline classes may have different configuration requirements and structure.

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

**Detailed Description**: Complete description of all configuration parameters, configuration examples, and links to real working files are available in the [Configuration Guide](docs/CONFIGURATION_GUIDE.md).

### Scheduled Restart Configuration

To manage scheduled restarts when running via `evileye run`, you can use the `controller.scheduled_restart` section:

```json
"controller": {
  "fps": 30,
  "show_main_gui": true,
  "scheduled_restart": {
    "enabled": false,
    "mode": "daily_time",
    "time": "01:00",
    "interval_minutes": 0
  }
}
```

- **enabled**: Enable/disable automatic restart (default: `false`).
- **mode**: Scheduler operation mode:
  - `"daily_time"` — restart once per day at the specified `time`.
  - `"interval"` — restart every `interval_minutes` minutes after the previous run completes (useful for testing, e.g., 5 minutes).
- **time**: Daily restart time in `HH:MM` format (default: `"01:00"`).
- **interval_minutes**: Interval in minutes for `"interval"` mode.

Scheduled restart only works when running via CLI `evileye run` and does not affect direct launch via `evileye-process`/`process.py`.

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

#### RT-DETR Detector Configuration

RT-DETR (Real-Time Detection Transformer) provides high-accuracy object detection with transformer architecture.

**Configuration Example**: [single_video_rtdetr.json](evileye/samples_configs/single_video_rtdetr.json)

Main parameters:
- `type`: `"ObjectDetectorRtdetr"`
- `model`: `"rtdetr-l.pt"` or `"rtdetr-x.pt"`
- `inference_size`: Input image size (usually 640)
- `conf`: Confidence threshold (usually 0.25)

**Example for multiple videos**: [multi_videos_rtdetr.json](evileye/samples_configs/multi_videos_rtdetr.json)

#### RF-DETR Detector Configuration

RF-DETR (Roboflow Detection Transformer) provides optimized transformer-based detection.

**Configuration Example**: [single_video_rfdetr.json](evileye/samples_configs/single_video_rfdetr.json)

Main parameters:
- `type`: `"ObjectDetectorRfdetr"`
- `model`: `"rfdetr-nano"` or other RF-DETR models
- `inference_size`: Input image size (usually 640)
- `conf`: Confidence threshold (usually 0.25)

#### Detector Types

| Detector Type | Model | Architecture | Speed | Accuracy |
|---------------|-------|--------------|-------|----------|
| YOLO | `yolov8n.pt` | CNN | Fast | Good |
| RT-DETR | `rtdetr-l.pt` | Transformer | Medium | High |
| RF-DETR | `rfdetr-nano` | Transformer | Fast | Good |

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

Detailed description of all configuration parameters and complete examples are available in the [Configuration Guide](docs/CONFIGURATION_GUIDE.md).

#### IP Camera Configuration

**Configuration Example**: [single_ip_camera.json](evileye/samples_configs/single_ip_camera.json)

Main features:
- Single IP camera source (RTSP stream)
- YOLO detector (yolo11n.pt)
- BoTSORT tracker
- Database enabled
- Authentication support via `username` and `password` or `credentials.json`

**Usage**:
```bash
evileye run configs/single_ip_camera.json
```

**Note**: Before using, update the camera URL in the configuration file or use `credentials.json` to store credentials.

#### Video File Configuration

**Configuration Example**: [single_video.json](evileye/samples_configs/single_video.json)

Main features:
- Single video file source
- YOLO detector
- BoTSORT tracker
- Database enabled

**Example with multiple videos**: [multi_videos.json](evileye/samples_configs/multi_videos.json)

Configuration for processing multiple video files with multi-camera tracking:
- Two or more video files
- Separate detectors and trackers for each source
- Multi-camera tracking enabled

**Example with video splitting**: [single_video_split.json](evileye/samples_configs/single_video_split.json)

Configuration for processing a single video file split into multiple regions:
- Single video file split into multiple regions
- Separate detectors and trackers for each region
- Useful for videos with multiple cameras in one file

**Usage**:
```bash
evileye run configs/single_video.json
evileye run configs/multi_videos.json
evileye run configs/single_video_split.json
```

#### Other Configuration Examples

- **RT-DETR detector**: [single_video_rtdetr.json](evileye/samples_configs/single_video_rtdetr.json), [multi_videos_rtdetr.json](evileye/samples_configs/multi_videos_rtdetr.json)
- **RF-DETR detector**: [single_video_rfdetr.json](evileye/samples_configs/single_video_rfdetr.json)
- **GStreamer backend**: [single_video_gstreamer.json](evileye/samples_configs/single_video_gstreamer.json), [ip_camera_gstreamer.json](evileye/samples_configs/ip_camera_gstreamer.json)
- **With attributes**: [single_video_with_attributes.json](evileye/samples_configs/single_video_with_attributes.json)
- **PipelineCapture**: [pipeline_capture.json](evileye/samples_configs/pipeline_capture.json)

All configuration examples are located in the `evileye/samples_configs/` folder and can be obtained using the `evileye deploy-samples` command.

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
| `evileye-srv` | FastAPI web server launcher | `evileye-srv [OPTIONS]` |

### Main CLI Commands (`evileye`)

The main `evileye` command provides access to all system functionality:

```bash
# Deploy configuration files to current directory
evileye deploy

# Deploy sample configurations with working examples
evileye deploy-samples

# Create new configuration
evileye create my_config --sources 2 --source-type video_file

# Run with configuration
evileye run configs/my_config.json

# Start FastAPI web server
evileye server --host 0.0.0.0 --port 8080

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

### Web Server (`evileye server` / `evileye-srv`)

FastAPI web server for remote access and API integration:

```bash
# Start web server with default settings (127.0.0.1:8080)
evileye server

# Start on specific host and port
evileye server --host 0.0.0.0 --port 8000

# Start with auto-run configuration
evileye server --config configs/single_video.json

# Disable auto-reload
evileye server --no-reload

# Set log level
evileye server --log-level debug
```

**Options:**
- `--host HOST` - Bind host (default: 127.0.0.1)
- `--port PORT` - Bind port (default: 8080)
- `--reload` / `--no-reload` - Auto-reload on code changes (default: enabled)
- `--workers N` - Number of worker processes (default: 1)
- `--config CONFIG` - Auto-run selected config after server starts
- `--log-level LEVEL` - Logging level (default: info)
- `--verbose` - Enable verbose logging

**API Documentation:**
- Interactive API docs: `http://localhost:8080/docs`
- ReDoc documentation: `http://localhost:8080/redoc`
- OpenAPI schema: `http://localhost:8080/openapi.json`

**Alternative entry point:**
```bash
# Use evileye-srv as alternative entry point
evileye-srv --host 0.0.0.0 --port 8080
```

### Configuration Creator (`evileye create`)

Command-line tool for creating new configuration files:

```bash
# Create basic configuration
evileye create my_config

# Create configuration with specific number of sources
evileye create my_config --sources 3

# Create configuration with specific source type
evileye create my_config --sources 2 --source-type ip_camera

# Create configuration with specific pipeline
evileye create my_config --pipeline PipelineSurveillance

# List available pipeline classes
evileye create --list-pipelines

# Create configuration in specific directory
evileye create /path/to/custom_config
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
2. Create configurations using `evileye create`
3. Run the system with `evileye run`

### Configuration Management

```bash
# List available pipeline classes
evileye create --list-pipelines

# Create configuration with specific pipeline
evileye create my_config --sources 2 --pipeline PipelineSurveillance

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
evileye create surveillance_config --sources 2 --source-type ip_camera

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
evileye create my_config --sources 3 --source-type ip_camera

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

# Use web server for API integration
evileye server --host 0.0.0.0 --port 8080 --config configs/api_config.json
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

EvilEye uses a modular pipeline architecture for processing video streams with support for object detection, tracking, and event analysis.

### Architecture Overview

The system is organized at several levels of abstraction:

1. **CLI and Entry Points** - Various ways to launch the system (CLI, GUI, API)
2. **Controller** - Central orchestrator coordinating all components
3. **Pipeline** - Modular video processing through a sequence of processors
4. **Video Capture and Recording** - Support for various backends (OpenCV, GStreamer)
5. **Object Processing** - Management of detected objects lifecycle
6. **Event Processing** - Detection and storage of various event types
7. **Database** - Data storage in PostgreSQL or JSON files

### Detailed Architecture Documentation

**[Complete System Architecture Description](docs/ARCHITECTURE.md)** - Detailed description of all architecture levels with diagrams and schemas.

The document includes:
- Component interaction diagrams at each level
- Data flow descriptions
- Implementation details of key components
- Class and sequence diagrams

### Pipeline Architecture

EvilEye uses a modular pipeline architecture:

1. **Sources** - Video capture from cameras, files, or streams
2. **Preprocessors** - Frame preprocessing and enhancement
3. **Detectors** - Object detection using YOLO, RT-DETR, RF-DETR models
4. **Trackers** - Object tracking and trajectory analysis
5. **Multi-camera Trackers** - Cross-camera object re-identification
6. **Attributes** - Detection and tracking of object attributes

Each component is implemented as a processor that can be configured and combined to create custom surveillance pipelines.

### Pipeline Classes

EvilEye supports multiple pipeline implementations:

- **PipelineSurveillance** - Full-featured pipeline with all components (sources, detectors, trackers, mc_trackers, attributes)
- **PipelineCapture** - Simplified pipeline for video capture
- **Custom Pipelines** - User-defined pipeline implementations

Pipeline classes are automatically discovered from:
- Built-in `evileye.pipelines` package
- Local `pipelines/` folder in working directory

#### Available Pipeline Classes

```bash
# List available pipeline classes
evileye create --list-pipelines
```

#### Creating Custom Pipelines

Create custom pipelines by extending the base `Pipeline` class and placing them in a local `pipelines/` folder:

```python
from evileye.core.pipeline_processors import PipelineProcessors


class MyCustomPipeline(PipelineProcessors):
    def __init__(self):
        super().__init__()
        # Custom initialization

    def generate_default_structure(self, num_sources: int):
        # Configuration structure generation
        pass
```

Each pipeline class can define its own configuration structure and processing logic.

For more details on creating pipelines, see [Pipeline Architecture Guide](docs/PIPELINE_ARCHITECTURE.md).

## Documentation

Detailed documentation is located in the [docs/](docs/) folder:

- **[Main Documentation Index](docs/README.md)** - Navigation for all documentation
- **[System Architecture](docs/ARCHITECTURE.md)** - Complete architecture description at 7 levels of abstraction with diagrams

### Main Documentation Sections

#### Architecture and Design

- **[System Architecture](docs/ARCHITECTURE.md)** - Detailed architecture description at all levels (CLI, Controller, Pipeline, Video, Objects, Events, Database) with interactive Mermaid diagrams and static UML diagrams
- **[Pipeline Architecture](docs/PIPELINE_ARCHITECTURE.md)** - Pipeline architecture description, base classes, and ways to create custom pipelines
- **[GUI Refactoring Guide](docs/GUI_REFACTORING_GUIDE.md)** - GUI system architecture, components, and best practices

#### Installation and Setup

- **[Database Setup Guide](docs/DATABASE_SETUP_GUIDE.md)** - Detailed PostgreSQL setup guide
- **[Deploy Command](docs/CLI_DEPLOY_COMMAND.md)** - Using the `evileye deploy` command to deploy the system
- **[Configuration Guide](docs/CONFIGURATION_GUIDE.md)** - Complete guide to configuration files structure, parameters, and examples
- **[Configuration Creation](docs/CREATE_SCRIPT_README.md)** - Using the `evileye create` command to create new configurations

#### Functionality

- **[Attributes Detection System](docs/ATTRIBUTES_DETECTION_README.md)** - Detection and tracking of object attributes (hard hat, backpack, etc.)
- **[Object Labeling System](docs/LABELING_SYSTEM_README.md)** - Automatic saving of object labels in JSON format
- **[Text Rendering System](docs/TEXT_RENDERING_SYSTEM.md)** - Adaptive text rendering with support for various resolutions
- **[Configuration History](docs/CONFIG_HISTORY_USER_GUIDE.md)** - User guide for working with configuration history

#### User Guides

- **[GStreamer Usage for Video](docs/VideoCaptureGStreamer_Usage.md)** - Setup and usage of GStreamer for video capture from IP cameras, USB cameras, and files
- **[GStreamer Usage for Image Sequences](docs/ImageSequence_GStreamer_Usage.md)** - Processing image sequences via GStreamer

### Quick Navigation

- **For New Users**: Start with [database setup](docs/DATABASE_SETUP_GUIDE.md) and [deploy command](docs/CLI_DEPLOY_COMMAND.md)
- **For Developers**: Study [system architecture](docs/ARCHITECTURE.md) and [pipeline architecture](docs/PIPELINE_ARCHITECTURE.md)
- **For Integrators**: Familiarize yourself with [GStreamer usage](docs/VideoCaptureGStreamer_Usage.md) and [attributes detection system](docs/ATTRIBUTES_DETECTION_README.md)

Historical development reports are located in the [reports/](reports/) folder.

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
