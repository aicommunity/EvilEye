"""
Test script to record a short video fragment from RTSP camera and return the path.
"""
import time
import sys
from pathlib import Path
import datetime
import tempfile

def test_record_video_fragment():
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    from evileye.video_recorder.recording_params import RecordingParams
    
    # Camera details
    camera_url = "rtsp://user:AutoZloboglaz821-@10.245.1.199"
    username = "user"
    password = "AutoZloboglaz821-"
    
    # Create temporary directory for recording
    tmp_dir = Path(tempfile.mkdtemp(prefix="evileye_test_"))
    print(f"Using temporary directory: {tmp_dir}")
    
    cap = VideoCaptureGStreamer()
    
    # Enable recording to save video fragment
    recording_params = RecordingParams(
        enabled=True,
        container="mp4",
        segment_length_sec=300,
        retention_days=3,
        min_free_space_pct=80,
        min_file_size_kb=500,
        out_dir=str(tmp_dir / "Recording"),
        filename_tmpl="{source_name}_{start_time}_{seq}.{ext}",
    )
    cap.recording_params = recording_params
    
    # Set parameters
    cap.set_params(
        source="IpCamera",
        camera=camera_url,
        source_ids=[0],
        source_names=["TestCam"],
        username=username,
        password=password,
    )
    
    print("Initializing camera connection...")
    init_result = cap.init()
    
    if not init_result:
        print("Failed to initialize camera connection")
        print("This may be due to network issues or camera being unavailable")
        return None
    
    print("Camera connected successfully!")
    print("Starting capture and recording...")
    cap.start()
    
    # Wait for frames to start coming
    print("Waiting for frames (3 seconds)...")
    time.sleep(3.0)
    
    frames = cap.get()
    print(f"Frames received: {len(frames)}")
    
    # Record for a few more seconds to get a video fragment
    print("Recording video fragment (5 seconds)...")
    time.sleep(5.0)
    
    print("Stopping capture...")
    cap.stop()
    cap.release()
    
    # Find recorded video files
    out_dir = Path(cap.recording_params.out_dir)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    date_dir = out_dir / today
    
    if date_dir.exists():
        video_files = list(date_dir.rglob("*.mp4"))
        if video_files:
            # Get the most recent file
            latest_file = max(video_files, key=lambda p: p.stat().st_mtime)
            print(f"\n=== Video Fragment Saved ===")
            print(f"Path: {latest_file.absolute()}")
            print(f"Size: {latest_file.stat().st_size / 1024:.2f} KB")
            print(f"\nTo read the video file, use:")
            print(f"  {latest_file.absolute()}")
            return str(latest_file.absolute())
        else:
            print("No video files found in recording directory")
    else:
        print(f"Recording directory does not exist: {date_dir}")
    
    return None
