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
        gui: Optional[bool] = typer.Option(True, "--gui", help="Launch with gui interface"),
        autoclose: Optional[bool] = typer.Option(True, "--autoclose", help="Automatic close application when video ends"),
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
    cmd = [sys.executable, "process.py", "--gui"]

    if config:
        if not config.exists():
            console.print(f"[red]Configuration file not found: {config}[/red]")
            raise typer.Exit(1)
        cmd.extend(["--config", str(config)])
    elif video:
        cmd.extend(["--video", video])
    else:
        # Use default config
        default_config = Path("configs/test_sources_detectors_trackers_mc.json")
        if default_config.exists():
            cmd.extend(["--config", str(default_config)])
        else:
            console.print("[red]No configuration file specified and default not found[/red]")
            console.print("Please specify a config file: [yellow]evileye gui <config_file>[/yellow]")
            raise typer.Exit(1)

    cmd.extend(["--gui", gui])
    cmd.extend(["--autoclose", autoclose])

    try:
        console.print(f"[green]Launching with command:[/green] {' '.join(cmd)}")
        # Change to project root directory before running
        os.chdir(Path(__file__).parent.parent)
        subprocess.run(cmd, check=True)
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
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """
    Validate EvilEye configuration file.
    
    Example:
        evileye validate configs/single_cam.json
    """
    try:
        with open(config, 'r') as f:
            pipeline_config = json.load(f)
        
        validate_config(pipeline_config)
        console.print(f"[green]Configuration {config} is valid![/green]")
        
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
