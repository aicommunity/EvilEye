#!/usr/bin/env python3
"""
Test memory usage of video recording modules.

Tests EventBuffer and EventRecorder with large numbers of frames.
"""

import os
import sys
import time
import numpy as np
from pathlib import Path
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.memory_profiler import MemoryProfiler
from evileye.video_recorder.event_buffer import EventBuffer
from evileye.video_recorder.event_recorder import EventRecorder
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import SourceMeta


def create_test_frame(width: int = 1920, height: int = 1080) -> np.ndarray:
    """Create a test frame."""
    return np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)


def test_event_buffer(max_duration: float = 60.0, fps: float = 30.0, 
                     test_duration: int = 300):
    """Test EventBuffer memory usage."""
    print("=" * 80)
    print("Testing EventBuffer")
    print("=" * 80)
    
    buffer = EventBuffer(max_duration_seconds=max_duration, fps=fps)
    profiler = MemoryProfiler(interval=2.0, leak_threshold_mb=10.0, leak_window=5)
    profiler.start_tracemalloc()
    
    initial_rss, _, _ = profiler.get_memory_stats()
    print(f"Initial RSS: {initial_rss:.2f} MB")
    print()
    
    start_time = time.time()
    frame_count = 0
    
    try:
        while time.time() - start_time < test_duration:
            # Add frames at FPS rate
            frame = create_test_frame()
            buffer.add_frame(frame, timestamp=time.time())
            frame_count += 1
            
            # Check memory every second
            if frame_count % int(fps) == 0:
                elapsed = time.time() - start_time
                rss_mb, vms_mb, _ = profiler.get_memory_stats()
                buffer_size = buffer.size()
                print(f"[{elapsed:6.1f}s] Frames: {frame_count:6d}, "
                      f"Buffer size: {buffer_size:4d}, "
                      f"RSS: {rss_mb:8.2f} MB, VMS: {vms_mb:8.2f} MB")
            
            time.sleep(1.0 / fps)
        
        # Test frame retrieval
        print("\nTesting frame retrieval...")
        test_timestamp = time.time()
        frames_before = buffer.get_frames_before(test_timestamp, seconds=10.0)
        print(f"Retrieved {len(frames_before)} frames before timestamp")
        
        # Clear buffer
        print("\nClearing buffer...")
        buffer.clear()
        time.sleep(2)
        
        final_rss, final_vms, _ = profiler.get_memory_stats()
        print(f"\nFinal RSS: {final_rss:.2f} MB")
        print(f"Memory growth: {final_rss - initial_rss:+.2f} MB")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    return buffer


def test_event_recorder(test_duration: int = 300):
    """Test EventRecorder memory usage."""
    print("=" * 80)
    print("Testing EventRecorder")
    print("=" * 80)
    
    # Create test source meta
    source_meta = SourceMeta(
        source_name="test_source",
        source_address="/tmp/test.mp4",
        source_type="VideoFile",
        width=1920,
        height=1080,
        fps=30.0
    )
    
    # Create recording params
    params = RecordingParams()
    params.enabled = True
    params.event_recording_enabled = True
    params.event_pre_seconds = 10.0
    params.event_post_seconds = 10.0
    params.container = "mp4"
    
    # Create event buffer
    event_buffer = EventBuffer(
        max_duration_seconds=params.event_pre_seconds + params.event_post_seconds,
        fps=30.0
    )
    
    # Create recorder
    recorder = EventRecorder(source_meta, params, event_buffer)
    
    profiler = MemoryProfiler(interval=2.0, leak_threshold_mb=10.0, leak_window=5)
    profiler.start_tracemalloc()
    
    initial_rss, _, _ = profiler.get_memory_stats()
    print(f"Initial RSS: {initial_rss:.2f} MB")
    print()
    
    start_time = time.time()
    frame_count = 0
    event_count = 0
    
    try:
        while time.time() - start_time < test_duration:
            frame = create_test_frame()
            timestamp = time.time()
            
            # Add to buffer
            event_buffer.add_frame(frame, timestamp)
            
            # Simulate events every 30 seconds
            if frame_count % 900 == 0 and frame_count > 0:
                event_count += 1
                print(f"\nStarting event {event_count} at {timestamp:.1f}s")
                recorder.start_event_recording(
                    event_id=event_count,
                    event_name=f"test_event_{event_count}",
                    event_timestamp=timestamp
                )
            
            # Add post-event frames if recording
            if recorder.is_recording():
                recorder.add_post_event_frame(frame, timestamp)
            
            frame_count += 1
            
            # Check memory every second
            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                rss_mb, vms_mb, _ = profiler.get_memory_stats()
                print(f"[{elapsed:6.1f}s] Frames: {frame_count:6d}, "
                      f"Events: {event_count}, "
                      f"Recording: {recorder.is_recording()}, "
                      f"RSS: {rss_mb:8.2f} MB, VMS: {vms_mb:8.2f} MB")
            
            time.sleep(1.0 / 30.0)
        
        # Stop all recordings
        print("\nStopping all recordings...")
        while recorder.is_recording():
            recorder.stop_event_recording()
            time.sleep(1)
        
        time.sleep(2)
        
        final_rss, final_vms, _ = profiler.get_memory_stats()
        print(f"\nFinal RSS: {final_rss:.2f} MB")
        print(f"Memory growth: {final_rss - initial_rss:+.2f} MB")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        if recorder.is_recording():
            recorder.stop_event_recording()
    
    return recorder, event_buffer


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Test recording memory usage')
    parser.add_argument('--test', choices=['buffer', 'recorder', 'both'], 
                       default='both', help='Test to run (default: both)')
    parser.add_argument('--duration', type=int, default=300,
                       help='Test duration in seconds (default: 300)')
    parser.add_argument('--buffer-duration', type=float, default=60.0,
                       help='EventBuffer max duration in seconds (default: 60.0)')
    parser.add_argument('--fps', type=float, default=30.0,
                       help='Frames per second (default: 30.0)')
    
    args = parser.parse_args()
    
    try:
        if args.test in ('buffer', 'both'):
            test_event_buffer(
                max_duration=args.buffer_duration,
                fps=args.fps,
                test_duration=args.duration
            )
            time.sleep(5)  # Wait for cleanup
        
        if args.test in ('recorder', 'both'):
            test_event_recorder(test_duration=args.duration)
            time.sleep(5)  # Wait for cleanup
        
        print("\n" + "=" * 80)
        print("All tests completed")
        print("=" * 80)
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
