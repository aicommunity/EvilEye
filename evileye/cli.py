#!/usr/bin/env python3
"""
EvilEye Command Line Interface

Provides command-line tools for running the EvilEye surveillance system.
"""

import json
import sys
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from evileye.utils.utils import normalize_config_path
from evileye.core.logging_config import setup_evileye_logging, log_system_info
from evileye.core.logger import get_module_logger


# Create CLI app
app = typer.Typer(
    name="evileye",
    help="Intelligence video surveillance system",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    level = "DEBUG" if verbose else "INFO"
    setup_evileye_logging(log_level=level, log_to_console=True, log_to_file=True)


@app.command()
def run(
        config: Optional[Path] = typer.Argument(None, help="Configuration file path"),
        video: Optional[str] = typer.Option(None, "--video", help="Video file to process"),
        gui: bool = typer.Option(True, "--gui/--no-gui", help="Launch with gui interface"),
        autoclose: bool = typer.Option(False, "--autoclose/--no-autoclose", help="Automatic close application when video ends"),
        verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging"),
) -> None:
    """
    Launch EvilEye 

    Example:
        evileye run configs/test_sources_detectors_trackers_mc.json
        evileye run --video /path/to/video.mp4
    """
    import subprocess
    import os

    # Setup logging
    setup_logging(verbose=verbose)
    logger = get_module_logger("cli")
    log_system_info(logger)

    # Build command arguments
    cmd = [sys.executable, str(Path(__file__).parent / "process.py")]

    if config:
        # Normalize config path and check if it exists
        normalized_config = Path(normalize_config_path(config))
        if not normalized_config.exists():
            logger.error(f"Configuration file not found: {normalized_config}")
            console.print(f"[red]Configuration file not found: {normalized_config}[/red]")
            raise typer.Exit(1)
        cmd.extend(["--config", str(normalized_config)])
        logger.info(f"Using configuration: {normalized_config}")
    elif video:
        cmd.extend(["--video", video])
        logger.info(f"Using video file: {video}")
    else:
        # Use default config
        default_config = Path("configs/test_sources_detectors_trackers_mc.json")
        if default_config.exists():
            cmd.extend(["--config", str(default_config)])
            logger.info(f"Using default configuration: {default_config}")
        else:
            logger.error("Configuration file not specified and default configuration not found")
            console.print("[red]No configuration file specified and default not found[/red]")
            console.print("Please specify a config file: [yellow]evileye run <config_file>[/yellow]")
            raise typer.Exit(1)

    # Add GUI flag based on boolean value
    if gui:
        cmd.append("--gui")
        logger.info("GUI enabled")
    else:
        cmd.append("--no-gui")
        logger.info("GUI disabled")

    # Add autoclose flag based on boolean value
    if autoclose:
        cmd.append("--autoclose")
        logger.info("Auto-close enabled")
    else:
        cmd.append("--no-autoclose")
        logger.info("Auto-close disabled")

    try:
        logger.info(f"Launching command: {' '.join(cmd)}")
        console.print(f"[green]Launching with command:[/green] {' '.join(cmd)}")
        # Run command in current working directory (where CLI was launched from)
        subprocess.run(cmd, check=True, cwd=os.getcwd())
        logger.info("Command executed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Launch error: {e}")
        console.print(f"[red]Error launching: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        logger.info("Launch interrupted by user")
        console.print("[yellow]Launch interrupted by user[/yellow]")
        raise typer.Exit(0)


@app.command()
def validate(
    config: Path = typer.Argument(
        ...,
        help="Path to configuration JSON file",
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """
    Validate EvilEye configuration file.
    
    Example:
        evileye validate single_cam.json
        evileye validate configs/single_cam.json
    """
    try:
        # Normalize config path
        normalized_config = Path(normalize_config_path(config))
        
        if not normalized_config.exists():
            console.print(f"[red]Configuration file not found: {normalized_config}[/red]")
            raise typer.Exit(1)
        
        with open(normalized_config, 'r') as f:
            pipeline_config = json.load(f)
        
        validate_config(pipeline_config)
        console.print(f"[green]Configuration {normalized_config} is valid![/green]")
        
    except Exception as e:
        console.print(f"[red]Configuration validation failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def list_configs() -> None:
    """
    List available configuration files.
    """
    config_dir = Path("configs")
    
    if not config_dir.exists():
        console.print("[red]Configs directory not found[/red]")
        raise typer.Exit(1)
    
    config_files = list(config_dir.glob("*.json"))
    
    if not config_files:
        console.print("[yellow]No configuration files found[/yellow]")
        return
    
    table = Table(title="Available Configurations")
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="magenta")
    table.add_column("Description", style="green")
    
    for config_file in sorted(config_files):
        size = config_file.stat().st_size
        description = get_config_description(config_file)
        
        table.add_row(
            config_file.name,
            f"{size} bytes",
            description,
        )
    
    console.print(table)


@app.command()
def deploy() -> None:
    """
    Deploy EvilEye configuration files to current directory.
    
    This command:
    1. Copies credentials_proto.json to credentials.json (if credentials.json doesn't exist)
    2. Creates configs folder if it doesn't exist
    """
    import shutil
    
    current_dir = Path.cwd()
    console.print(f"[blue]Deploying EvilEye files to: {current_dir}[/blue]")
    
    # Step 1: Copy credentials_proto.json to credentials.json
    credentials_proto = Path(__file__).parent / "credentials_proto.json"
    credentials_target = current_dir / "credentials.json"
    
    if credentials_target.exists():
        console.print("[yellow]credentials.json already exists, skipping...[/yellow]")
    else:
        if credentials_proto.exists():
            try:
                shutil.copy2(credentials_proto, credentials_target)
                console.print(f"[green]Copied credentials_proto.json to credentials.json[/green]")
            except Exception as e:
                console.print(f"[red]Error copying credentials file: {e}[/red]")
                raise typer.Exit(1)
        else:
            console.print("[red]credentials_proto.json not found in package[/red]")
            raise typer.Exit(1)
    
    # Step 2: Create configs folder
    configs_dir = current_dir / "configs"
    if configs_dir.exists():
        console.print("[yellow]configs folder already exists, skipping...[/yellow]")
    else:
        try:
            configs_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]Created configs folder[/green]")
        except Exception as e:
            console.print(f"[red]Error creating configs folder: {e}[/red]")
            raise typer.Exit(1)
    
    console.print("[green]Deployment completed successfully![/green]")


@app.command()
def deploy_samples() -> None:
    """
    Deploy sample configurations with working examples.
    
    This command:
    1. Runs regular deploy command
    2. Downloads sample videos from internet
    3. Copies pre-configured sample configurations
    4. Creates documentation for samples
    """
    import shutil
    
    current_dir = Path.cwd()
    console.print(f"[blue]Deploying EvilEye sample configurations to: {current_dir}[/blue]")
    
    # First run regular deploy
    deploy()
    
    # Create videos directory
    videos_dir = current_dir / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir()
        console.print("[green]Created videos folder[/green]")
    else:
        console.print("[yellow]videos folder already exists, skipping...[/yellow]")
    
    # Download sample videos
    console.print("\n[blue]Downloading sample videos...[/blue]")
    try:
        from evileye.utils.download_samples import download_sample_videos
        video_results = download_sample_videos(str(videos_dir), parallel=False)
        
        successful_videos = sum(1 for r in video_results.values() 
                              if "downloaded" in r["status"] or r["status"] == "exists")
        total_videos = len(video_results)
        
        if successful_videos > 0:
            console.print(f"[green]Downloaded {successful_videos}/{total_videos} sample videos[/green]")
        else:
            console.print("[yellow]No videos downloaded, but continuing with sample configs...[/yellow]")
            
    except Exception as e:
        console.print(f"[yellow]Video download failed: {e}[/yellow]")
        console.print("[blue]Continuing with sample configs (you can add videos manually)...[/blue]")
    
    # Copy sample configurations
    console.print("\n[blue]Copying sample configurations...[/blue]")
    samples_dir = Path(__file__).parent / "samples_configs"
    configs_dir = current_dir / "configs"
    
    sample_configs = [
        "single_video.json",
        "single_video_split.json", 
        "single_ip_camera.json",
        "multi_videos.json",
        "pipeline_capture.json",
        "single_video_rtdetr.json",
        "multi_videos_rtdetr.json",
        "single_video_rfdetr.json",
        "single_video_gstreamer.json",
        "ip_camera_gstreamer.json",
        "usb_camera_gstreamer.json",
        "image_sequence_gstreamer_jpg.json",
        "image_sequence_gstreamer_folder.json"
    ]
    
    copied_count = 0
    for config_name in sample_configs:
        source_path = samples_dir / config_name
        dest_path = configs_dir / config_name
        
        if source_path.exists():
            shutil.copy2(source_path, dest_path)
            console.print(f"[green]Copied {config_name}[/green]")
            copied_count += 1
        else:
            console.print(f"[yellow]Sample config {config_name} not found[/yellow]")
    
    # Create README for samples
    readme_content = """# EvilEye Sample Configurations

This directory contains sample configurations for EvilEye system.

## Available Samples:

### Video Processing
- **single_video.json** - Single video file processing (planes_sample.mp4)
- **single_video_split.json** - Single video with 2-way split processing (sample_split.mp4)
- **multi_videos.json** - Multiple video files with multi-camera tracking (6p-c0.avi, 6p-c1.avi)
- **single_video_gstreamer.json** - Single video file processing with GStreamer backend (planes_sample.mp4)

### GStreamer Backend Examples
- **ip_camera_gstreamer.json** - IP camera stream processing with GStreamer backend (RTSP)
- **usb_camera_gstreamer.json** - USB camera processing with GStreamer backend (/dev/video0)
- **image_sequence_gstreamer_jpg.json** - JPEG image sequence processing with GStreamer backend
- **image_sequence_gstreamer_folder.json** - All images in folder processing with GStreamer backend

### RT-DETR Detector Examples
- **single_video_rtdetr.json** - Single video with RT-DETR detector (planes_sample.mp4)
- **multi_videos_rtdetr.json** - Multiple videos with RT-DETR detector (6p-c0.avi, 6p-c1.avi)

### RF-DETR Detector Examples
- **single_video_rfdetr.json** - Single video with RF-DETR detector (planes_sample.mp4)

### IP Camera Processing  
- **single_ip_camera.json** - Single IP camera stream processing

## Video Files:

The following video files are downloaded to `videos/` directory:
- **planes_sample.mp4** - Sample video with planes for single video processing
- **sample_split.mp4** - Video with two camera views for split processing
- **6p-c0.avi** - Multi-camera tracking video (camera 0)
- **6p-c1.avi** - Multi-camera tracking video (camera 1)

## Usage:

```bash
# Run single video example
evileye run configs/single_video.json

# Run video split example  
evileye run configs/single_video_split.json

# Run multi-video example
evileye run configs/multi_videos.json

# Run IP camera example
evileye run configs/single_ip_camera.json

# Run RT-DETR examples
evileye run configs/single_video_rtdetr.json
evileye run configs/multi_videos_rtdetr.json

# Run RF-DETR example
evileye run configs/single_video_rfdetr.json

# Run GStreamer examples
evileye run configs/single_video_gstreamer.json
evileye run configs/ip_camera_gstreamer.json
evileye run configs/usb_camera_gstreamer.json
evileye run configs/image_sequence_gstreamer_jpg.json
evileye run configs/image_sequence_gstreamer_folder.json
```

## Configuration Features:

### Single Video (single_video.json)
- Processes planes_sample.mp4
- Single camera view
- Object detection and tracking
- Enhanced text rendering with 42pt font size

### Video Split (single_video_split.json)
- Processes sample_split.mp4 with 2-way split
- Two camera views from single video
- Separate detection and tracking for each view
- Multi-camera tracking disabled

### Multi Videos (multi_videos.json)
- Processes 6p-c0.avi and 6p-c1.avi
- Multi-camera tracking enabled
- Cross-camera object association
- Enhanced text rendering

### IP Camera (single_ip_camera.json)
- IP camera stream processing
- Real-time object detection
- Enhanced text rendering

### RT-DETR Detectors
- **single_video_rtdetr.json** - Single video with RT-DETR detector
- **multi_videos_rtdetr.json** - Multiple videos with RT-DETR detector
- Uses Ultralytics RT-DETR model (rtdetr-l.pt)
- Real-time detection transformer architecture
- High accuracy object detection

### RF-DETR Detector
- **single_video_rfdetr.json** - Single video with RF-DETR detector
- Uses Roboflow RF-DETR model (rfdetr-nano)
- Transformer-based real-time detection
- Optimized for speed and accuracy

## Notes:

- Sample videos are downloaded to `videos/` directory
- All configurations include admin database credentials
- Enhanced text rendering with configurable font sizes
- Background can be enabled/disabled via text_config

## Customization:

You can modify these configurations or use them as templates:
```bash
# Create your own config based on samples
evileye-create my_config --sources 2 --pipeline PipelineSurveillance
```

For more information, see the main README.md file.
"""
    
    readme_path = configs_dir / "README_SAMPLES.md"
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    console.print(f"[green]Copied {copied_count} sample configurations[/green]")
    console.print("[green]Created README_SAMPLES.md[/green]")
    
    console.print("\n[green]Sample deployment completed successfully![/green]")
    console.print("\n[blue]Available sample configurations:[/blue]")
    for config_name in sample_configs:
        if (configs_dir / config_name).exists():
            console.print(f"  [yellow]- {config_name}[/yellow]")
    
    console.print("\n[blue]Try running a sample:[/blue]")
    console.print("  [yellow]evileye run configs/single_video.json[/yellow]")
    console.print("\n[blue]Downloaded video files:[/blue]")
    for video_name in ["planes_sample.mp4", "sample_split.mp4", "6p-c0.avi", "6p-c1.avi"]:
        if (videos_dir / video_name).exists():
            console.print(f"  [green]{video_name}[/green]")
        else:
            console.print(f"  [yellow]{video_name} (not downloaded)[/yellow]")


@app.command()
def create(
    config_name: str = typer.Argument(None, help="Configuration name"),
    sources: int = typer.Option(0, "--sources", help="Number of sources"),
    pipeline: str = typer.Option("PipelineSurveillance", "--pipeline", help="Pipeline class"),
    source_type: str = typer.Option("video_file", "--source-type", help="Source type"),
    output_dir: str = typer.Option("configs", "--output-dir", help="Output directory"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing file"),
    list_pipelines: bool = typer.Option(False, "--list-pipelines", help="List available pipelines"),
    detector_model: Optional[str] = typer.Option(None, "--detector-model", help="Detector model path"),
    tracker_type: Optional[str] = typer.Option(None, "--tracker-type", help="Tracker type"),
    db_enabled: Optional[bool] = typer.Option(None, "--db/--no-db", help="Enable/disable database"),
) -> None:
    """
    Create new EvilEye configuration file.
    
    Examples:
        evileye create my_config --sources 2
        evileye create my_config --sources 1 --source-type ip_camera
        evileye create test --pipeline PipelineSurveillance --sources 3
        evileye create --list-pipelines
    """
    import os
    import json
    from pathlib import Path
    from evileye.controller.controller import Controller
    
    # Handle list pipelines
    if list_pipelines:
        try:
            controller_instance = Controller()
            pipeline_classes = controller_instance.get_available_pipeline_classes()
            
            if not pipeline_classes:
                console.print("[yellow]No pipeline classes found.[/yellow]")
                return
            
            table = Table(title="Available Pipeline Classes")
            table.add_column("Index", style="cyan")
            table.add_column("Class Name", style="green")
            
            for i, class_name in enumerate(pipeline_classes, 1):
                table.add_row(str(i), class_name)
            
            console.print(table)
            console.print(f"\n[blue]Total: {len(pipeline_classes)} pipeline class(es)[/blue]")
            console.print("[blue]Use --pipeline <class_name> to specify a pipeline when creating a configuration.[/blue]")
            return
            
        except Exception as e:
            console.print(f"[red]Error listing pipeline classes: {e}[/red]")
            raise typer.Exit(1)
    
    # Validate config_name is provided when not listing pipelines
    if not config_name:
        console.print("[red]Configuration name is required![/red]")
        console.print("[yellow]Usage: evileye create <config_name>[/yellow]")
        console.print("[yellow]Use --help for more information.[/yellow]")
        raise typer.Exit(1)
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Determine output file path
    if not config_name.endswith('.json'):
        config_name += '.json'
    
    output_path = os.path.join(output_dir, config_name)
    
    # Check if file already exists
    if os.path.exists(output_path) and not force:
        console.print(f"[red]Configuration file '{output_path}' already exists![/red]")
        console.print("[yellow]Use --force to overwrite or choose a different name.[/yellow]")
        raise typer.Exit(1)
    
    # Build optional parameters
    detector_params = {}
    if detector_model:
        detector_params['model_path'] = detector_model
    
    tracker_params = {}
    if tracker_type:
        tracker_params['tracker_type'] = tracker_type
    
    database_params = {}
    if db_enabled is not None:
        # Only pass safe database parameters (no credentials)
        database_params = {
            "image_dir": "EvilEyeData",
            "preview_width": 300,
            "preview_height": 150
        }
    
    # Create configuration
    console.print(f"[blue]Creating configuration:[/blue]")
    console.print(f"   Pipeline: {pipeline}")
    console.print(f"   Sources: {sources}")
    console.print(f"   Source type: {source_type}")
    console.print(f"   Output: {output_path}")
    
    try:
        controller_instance = Controller()
        config_data = controller_instance.create_config(
            num_sources=sources,
            pipeline_class=pipeline,
            source_type=source_type,
            detector_params=detector_params if detector_params else None,
            tracker_params=tracker_params if tracker_params else None,
            database_params=database_params if database_params else None
        )
        
        # Write configuration to file
        with open(output_path, 'w') as f:
            json.dump(config_data, f, indent=4)
        
        console.print(f"[green]Configuration created successfully![/green]")
        console.print(f"   File: {output_path}")
        console.print(f"   Size: {os.path.getsize(output_path)} bytes")
        
    except Exception as e:
        console.print(f"[red]Error creating configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def info() -> None:
    """
    Display EvilEye system information.
    """
    from . import __version__
    
    table = Table(title="EvilEye System Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Version", __version__)
    table.add_row("Python", sys.version)
    table.add_row("Platform", sys.platform)
    
    # Check for GPU support
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info = f"CUDA {torch.version.cuda} ({torch.cuda.device_count()} devices)"
        else:
            gpu_info = "Not available"
    except ImportError:
        gpu_info = "PyTorch not installed"
    
    table.add_row("GPU Support", gpu_info)
    
    # Check for OpenCV
    try:
        import cv2
        opencv_version = cv2.__version__
    except ImportError:
        opencv_version = "Not installed"
    
    table.add_row("OpenCV", opencv_version)
    
    console.print(table)


def validate_config(config: dict) -> None:
    """Validate pipeline configuration"""
    required_sections = ["pipeline"]
    
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required section: {section}")
    
    pipeline_config = config.get("pipeline", {})
    required_pipeline_sections = ["sources"]
    
    for section in required_pipeline_sections:
        if section not in pipeline_config:
            raise ValueError(f"Missing required pipeline section: {section}")
    
    # Validate sources
    sources = pipeline_config.get("sources", [])
    if not sources:
        raise ValueError("At least one source must be configured")
    
    for i, source in enumerate(sources):
        if "source" not in source:
            raise ValueError(f"Source {i}: missing 'source' field")
        if "camera" not in source:
            raise ValueError(f"Source {i}: missing 'camera' field")


def get_config_description(config_file: Path) -> str:
    """Get description for configuration file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        pipeline_config = config.get("pipeline", {})
        sources = pipeline_config.get("sources", [])
        
        if not sources:
            return "No sources configured"
        
        source_types = [source.get("source", "unknown") for source in sources]
        return f"{len(sources)} source(s): {', '.join(source_types)}"
        
    except Exception:
        return "Invalid configuration"


def main() -> None:
    """Main entry point for CLI"""
    app()


if __name__ == "__main__":
    main()
