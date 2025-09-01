"""
EvilEye - Intelligence video surveillance system

A comprehensive video surveillance system with object detection, tracking,
and multi-camera support.
"""

__version__ = "1.0.0"
__author__ = "EvilEye Team"
__email__ = "team@evileye.com"

# Import core components
from .core import PipelineProcessors, ProcessorBase, ProcessorSource, ProcessorFrame, ProcessorStep
from .pipelines import PipelineSurveillance

# Import registered classes
from .capture import video_capture
from .object_detector import object_detection_yolo
from .object_tracker import object_tracking_botsort
from .object_multi_camera_tracker import ObjectMultiCameraTracking

# Import main modules
from . import process
from . import configure
from . import controller

# Define public API
__all__ = [
    # Core components
    "Pipeline",
    "ProcessorBase", 
    "ProcessorSource",
    "ProcessorFrame",
    "ProcessorStep",
    "PipelineSurveillance",
    
    # Registered classes
    "video_capture",
    "object_detection_yolo", 
    "object_tracking_botsort",
    "ObjectMultiCameraTracking",
    
    # Main modules
    "process",
    "configure", 
    "controller",
]

# Auto-fix entry points on first import
def _auto_fix_entry_points():
    """Automatically fix entry points when package is imported"""
    import os
    import subprocess
    from pathlib import Path
    
    # Only run once per session
    if hasattr(_auto_fix_entry_points, '_run'):
        return
    _auto_fix_entry_points._run = True
    
    try:
        # Get the project root directory
        package_dir = Path(__file__).parent
        project_root = package_dir.parent
        fix_script = project_root / "fix_entry_points.sh"
        
        if fix_script.exists() and os.access(fix_script, os.X_OK):
            # Run the fix script silently
            result = subprocess.run(
                [str(fix_script)],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode == 0:
                print("✅ EvilEye entry points automatically fixed")
            else:
                print(f"⚠️  Warning: Could not auto-fix entry points: {result.stderr}")
                
    except Exception as e:
        # Don't fail the import if fixing fails
        pass

# Call auto-fix function (only if not imported as module)
if __name__ != "__main__":
    _auto_fix_entry_points()
