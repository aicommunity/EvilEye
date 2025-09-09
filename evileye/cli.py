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


# Create CLI app
app = typer.Typer(
    name="evileye",
    help="Intelligence video surveillance system",
    add_completion=False,
)

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("evileye.log"),
        ],
    )


@app.command()
def run(
        config: Optional[Path] = typer.Argument(None, help="Configuration file path"),
        video: Optional[str] = typer.Option(None, "--video", help="Video file to process"),
        gui: bool = typer.Option(True, "--gui/--no-gui", help="Launch with gui interface"),
        autoclose: bool = typer.Option(False, "--autoclose/--no-autoclose", help="Automatic close application when video ends"),
) -> None:
    """
    Launch EvilEye 

    Example:
        evileye run configs/test_sources_detectors_trackers_mc.json
        evileye run --video /path/to/video.mp4
    """
    import subprocess
    import os

    # Build command arguments
    cmd = [sys.executable, str(Path(__file__).parent / "process.py")]

    if config:
        # Normalize config path and check if it exists
        normalized_config = Path(normalize_config_path(config))
        if not normalized_config.exists():
            console.print(f"[red]Configuration file not found: {normalized_config}[/red]")
            raise typer.Exit(1)
        cmd.extend(["--config", str(normalized_config)])
    elif video:
        cmd.extend(["--video", video])
    else:
        # Use default config
        default_config = Path("configs/test_sources_detectors_trackers_mc.json")
        if default_config.exists():
            cmd.extend(["--config", str(default_config)])
        else:
            console.print("[red]No configuration file specified and default not found[/red]")
            console.print("Please specify a config file: [yellow]evileye run <config_file>[/yellow]")
            raise typer.Exit(1)

    # Add GUI flag based on boolean value
    if gui:
        cmd.append("--gui")
    else:
        cmd.append("--no-gui")

    # Add autoclose flag based on boolean value
    if autoclose:
        cmd.append("--autoclose")
    else:
        cmd.append("--no-autoclose")

    try:
        console.print(f"[green]Launching with command:[/green] {' '.join(cmd)}")
        # Run command in current working directory (where CLI was launched from)
        subprocess.run(cmd, check=True, cwd=os.getcwd())
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error launching: {e}[/red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
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
                console.print(f"[green]✓ Copied credentials_proto.json to credentials.json[/green]")
            except Exception as e:
                console.print(f"[red]✗ Error copying credentials file: {e}[/red]")
                raise typer.Exit(1)
        else:
            console.print("[red]✗ credentials_proto.json not found in package[/red]")
            raise typer.Exit(1)
    
    # Step 2: Create configs folder
    configs_dir = current_dir / "configs"
    if configs_dir.exists():
        console.print("[yellow]configs folder already exists, skipping...[/yellow]")
    else:
        try:
            configs_dir.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]✓ Created configs folder[/green]")
        except Exception as e:
            console.print(f"[red]✗ Error creating configs folder: {e}[/red]")
            raise typer.Exit(1)
    
    console.print("[green]✓ Deployment completed successfully![/green]")
    console.print(f"[blue]You can now create configurations with:[/blue]")
    console.print(f"[yellow]  evileye-create my_config --sources 1[/yellow]")


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
    console.print(f"[blue]🎬 Deploying EvilEye sample configurations to: {current_dir}[/blue]")
    
    # First run regular deploy
    deploy()
    
    # Create videos directory
    videos_dir = current_dir / "videos"
    if not videos_dir.exists():
        videos_dir.mkdir()
        console.print("[green]✓ Created videos folder[/green]")
    else:
        console.print("[yellow]videos folder already exists, skipping...[/yellow]")
    
    # Download sample videos
    console.print("\n[blue]📥 Downloading sample videos...[/blue]")
    try:
        from evileye.utils.download_samples import download_sample_videos
        video_results = download_sample_videos(str(videos_dir))
        
        successful_videos = sum(1 for r in video_results.values() 
                              if "downloaded" in r["status"] or r["status"] == "exists")
        total_videos = len(video_results)
        
        if successful_videos > 0:
            console.print(f"[green]✓ Downloaded {successful_videos}/{total_videos} sample videos[/green]")
        else:
            console.print("[yellow]⚠️  No videos downloaded, but continuing with sample configs...[/yellow]")
            
    except Exception as e:
        console.print(f"[yellow]⚠️  Video download failed: {e}[/yellow]")
        console.print("[blue]Continuing with sample configs (you can add videos manually)...[/blue]")
    
    # Copy sample configurations
    console.print("\n[blue]📋 Copying sample configurations...[/blue]")
    samples_dir = Path(__file__).parent / "samples_configs"
    configs_dir = current_dir / "configs"
    
    sample_configs = [
        "single_video.json",
        "single_video_split.json", 
        "single_ip_camera.json",
        "multi_videos.json",
        "pipeline_capture.json"
    ]
    
    copied_count = 0
    for config_name in sample_configs:
        source_path = samples_dir / config_name
        dest_path = configs_dir / config_name
        
        if source_path.exists():
            shutil.copy2(source_path, dest_path)
            console.print(f"[green]✓ Copied {config_name}[/green]")
            copied_count += 1
        else:
            console.print(f"[yellow]⚠️  Sample config {config_name} not found[/yellow]")
    
    # Create README for samples
    readme_content = """# EvilEye Sample Configurations

This directory contains sample configurations for EvilEye system.

## Available Samples:

### Video Processing
- **single_video.json** - Single video file processing (planes_sample.mp4)
- **single_video_split.json** - Single video with 2-way split processing (sample_split.mp4)
- **multi_videos.json** - Multiple video files with multi-camera tracking (6p-c0.avi, 6p-c1.avi)

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
    
    console.print(f"[green]✓ Copied {copied_count} sample configurations[/green]")
    console.print("[green]✓ Created README_SAMPLES.md[/green]")
    
    console.print("\n[green]🎉 Sample deployment completed successfully![/green]")
    console.print("\n[blue]📋 Available sample configurations:[/blue]")
    for config_name in sample_configs:
        if (configs_dir / config_name).exists():
            console.print(f"  [yellow]• {config_name}[/yellow]")
    
    console.print("\n[blue]🚀 Try running a sample:[/blue]")
    console.print("  [yellow]evileye run configs/single_video.json[/yellow]")
    console.print("\n[blue]📁 Downloaded video files:[/blue]")
    for video_name in ["planes_sample.mp4", "sample_split.mp4", "6p-c0.avi", "6p-c1.avi"]:
        if (videos_dir / video_name).exists():
            console.print(f"  [green]✓ {video_name}[/green]")
        else:
            console.print(f"  [yellow]⚠️  {video_name} (not downloaded)[/yellow]")


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
