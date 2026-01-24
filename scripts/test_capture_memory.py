#!/usr/bin/env python3
"""
Test memory usage of video capture module.

Tests GStreamer capture with different configurations and monitors memory usage.
"""

import os
import sys
import time
import subprocess
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.memory_profiler import MemoryProfiler
from scripts.diagnose_gstreamer_issues import GStreamerDiagnostics


def create_test_config(video_file: str, use_gstreamer: bool = True, 
                      split_stream: bool = False, recording: bool = False) -> str:
    """Create a test configuration JSON."""
    import json
    
    config = {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [{
                "split": split_stream,
                "num_split": 2 if split_stream else 0,
                "src_coords": [[0, 0, 1920, 1080], [0, 1080, 1920, 1080]] if split_stream else [],
                "source_ids": [0, 1] if split_stream else [0],
                "desired_fps": None,
                "source_names": ["Test1", "Test2"] if split_stream else ["Test1"],
                "loop_play": True,
                "source": "VideoFile",
                "camera": video_file,
                "type": "VideoCaptureGStreamer" if use_gstreamer else "VideoCaptureOpencv"
            }],
            "detectors": [],
            "trackers": [],
            "mc_trackers": []
        },
        "events_detectors": {},
        "events_processor": {},
        "visualizer": {
            "source_ids": [0] if not split_stream else [0, 1],
            "show_debug_info": False,
            "fps": [30],
            "num_height": 1,
            "num_width": 1
        },
        "record": {
            "enabled": recording,
            "continuous_recording_enabled": recording,
            "event_recording_enabled": False,
            "container": "mp4",
            "segment_length_sec": 60,
            "retention_days": 1
        },
        "controller": {
            "autoclose": False,
            "fps": 30,
            "show_main_gui": False,
            "gui_enabled": False
        }
    }
    
    config_path = project_root / "configs" / "test_capture_memory.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    return str(config_path)


def run_capture_test(config_path: str, duration: int = 300, 
                    memory_interval: float = 5.0, 
                    enable_diagnostics: bool = False):
    """Run capture test with memory monitoring."""
    print(f"Starting capture test with config: {config_path}")
    print(f"Duration: {duration}s, Memory sampling: {memory_interval}s")
    if enable_diagnostics:
        print("Automatic diagnostics: ENABLED")
    print("-" * 80)
    
    # Start process
    cmd = [
        sys.executable,
        str(project_root / "evileye" / "process.py"),
        "--config", config_path,
        "--no-gui",
        "--log-level", "INFO"
    ]
    
    print(f"Command: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(project_root)
    )
    
    print(f"Process started with PID: {process.pid}")
    
    # Wait a bit for initialization
    time.sleep(5)
    
    # Start memory profiler
    profiler = MemoryProfiler(
        pid=process.pid,
        interval=memory_interval,
        leak_threshold_mb=20.0,
        leak_window=6
    )
    profiler.start_tracemalloc()
    
    # Start diagnostics if enabled
    diagnostics = None
    if enable_diagnostics:
        diagnostics = GStreamerDiagnostics(
            config_path=config_path,
            process_pid=process.pid
        )
        # Start diagnostics in background thread
        import threading
        diagnostics_thread = threading.Thread(
            target=diagnostics.run_diagnostic_loop,
            args=(duration, memory_interval),
            daemon=True
        )
        diagnostics_thread.start()
    
    try:
        # Monitor for specified duration
        start_time = time.time()
        while time.time() - start_time < duration:
            if process.poll() is not None:
                print(f"\nProcess exited with code {process.returncode}")
                stdout, stderr = process.communicate()
                if stdout:
                    print("STDOUT:", stdout.decode()[-1000:])
                if stderr:
                    print("STDERR:", stderr.decode()[-1000:])
                break
            
            time.sleep(memory_interval)
            rss_mb, vms_mb, _ = profiler.get_memory_stats()
            elapsed = time.time() - start_time
            print(f"[{elapsed:6.1f}s] RSS: {rss_mb:8.2f} MB, VMS: {vms_mb:8.2f} MB")
        
        # Stop process
        print("\nStopping process...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        
        # Final memory check
        time.sleep(2)
        final_rss, final_vms, _ = profiler.get_memory_stats()
        print(f"\nFinal memory after stop: RSS: {final_rss:.2f} MB, VMS: {final_vms:.2f} MB")
        
        # Generate diagnostics report if enabled
        if diagnostics:
            diagnostics.running = False
            time.sleep(2)  # Wait for diagnostics to finish
            report = diagnostics.generate_report()
            print("\n" + "=" * 80)
            print("DIAGNOSTICS REPORT")
            print("=" * 80)
            print(report)
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        if diagnostics:
            diagnostics.running = False
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    
    return process.returncode


def main():
    parser = argparse.ArgumentParser(description='Test capture memory usage')
    parser.add_argument('--video', type=str, required=True,
                       help='Path to test video file')
    parser.add_argument('--duration', type=int, default=300,
                       help='Test duration in seconds (default: 300)')
    parser.add_argument('--gstreamer', action='store_true', default=True,
                       help='Use GStreamer capture (default: True)')
    parser.add_argument('--opencv', action='store_true',
                       help='Use OpenCV capture instead of GStreamer')
    parser.add_argument('--split', action='store_true',
                       help='Test with split stream')
    parser.add_argument('--recording', action='store_true',
                       help='Test with recording enabled')
    parser.add_argument('--interval', type=float, default=5.0,
                       help='Memory sampling interval in seconds (default: 5.0)')
    parser.add_argument('--diagnostics', action='store_true',
                       help='Enable automatic diagnostics and issue fixing')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video):
        print(f"ERROR: Video file not found: {args.video}")
        sys.exit(1)
    
    use_gstreamer = args.gstreamer and not args.opencv
    
    config_path = create_test_config(
        args.video,
        use_gstreamer=use_gstreamer,
        split_stream=args.split,
        recording=args.recording
    )
    
    print(f"Test configuration:")
    print(f"  Video: {args.video}")
    print(f"  Backend: {'GStreamer' if use_gstreamer else 'OpenCV'}")
    print(f"  Split stream: {args.split}")
    print(f"  Recording: {args.recording}")
    print(f"  Duration: {args.duration}s")
    print()
    
    try:
        return_code = run_capture_test(
            config_path, 
            args.duration, 
            args.interval,
            enable_diagnostics=args.diagnostics
        )
        sys.exit(return_code or 0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
