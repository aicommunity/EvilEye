"""
Test RTSP connection to specific camera: rtsp://user:AutoZloboglaz821-@10.245.1.199
This test helps debug connection issues with GStreamer pipeline.
"""
import time
import pytest
from pathlib import Path


def test_rtsp_connection_specific_camera_tcp(tmp_path):
    """
    Test connection to specific RTSP camera using TCP protocol.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    
    # Camera details
    camera_url = "rtsp://user:AutoZloboglaz821-@10.245.1.199"
    username = "user"
    password = "AutoZloboglaz821-"
    
    cap = VideoCaptureGStreamer()
    
    # Set parameters
    cap.set_params(
        source="IpCamera",
        camera=camera_url,
        source_ids=[0],
        source_names=["TestCam"],
        username=username,
        password=password,
    )
    
    # Note: We use simple pipeline like in api-refactoring (no protocols parameter)
    # Build pipeline string
    pipeline_str = cap._build_pipeline()
    print(f"\n=== Pipeline String ===")
    print(pipeline_str)
    
    # Verify pipeline contains expected elements
    assert "rtspsrc" in pipeline_str, "Pipeline should contain rtspsrc"
    assert "rtph265depay" in pipeline_str or "rtph264depay" in pipeline_str, "Pipeline should contain RTP depay"
    assert "videoconvert" in pipeline_str, "Pipeline should contain videoconvert"
    
    # Try to initialize with detailed error logging
    print("\nAttempting to initialize with TCP protocol...")
    print("Enabling detailed logging...")
    
    import logging
    logging.basicConfig(level=logging.DEBUG)
    cap.logger.setLevel(logging.DEBUG)
    
    # Also try to get more details from GStreamer
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.debug_set_default_threshold(Gst.DebugLevel.WARNING)
    except Exception:
        pass
    
    init_result = cap.init()
    
    print(f"Init result: {init_result}")
    print(f"Is initialized: {cap.is_inited}")
    print(f"Is working: {cap.is_working}")
    
    if init_result:
        print("\n=== Connection Successful ===")
        cap.start()
        
        # Wait a bit for frames to start coming
        print("Waiting for frames...")
        time.sleep(3.0)
        
        frames = cap.get()
        print(f"Frames received: {len(frames)}")
        
        if frames:
            print(f"First frame shape: {frames[0].image.shape if hasattr(frames[0], 'image') and frames[0].image is not None else 'None'}")
        
        # Record for a few more seconds to get a video fragment
        print("Recording video fragment (5 seconds)...")
        time.sleep(5.0)
        
        cap.stop()
        cap.release()
        
        # Find recorded video files
        from pathlib import Path
        import datetime
        if hasattr(cap, 'recording_params') and cap.recording_params and cap.recording_params.enabled:
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
                    # Test functions should return None, not values
    else:
        print("\n=== Connection Failed ===")
        if hasattr(cap, '_last_init_error') and cap._last_init_error:
            print(f"Last init error: {cap._last_init_error}")


def test_rtsp_connection_specific_camera(tmp_path):
    """
    Test connection to specific RTSP camera: rtsp://user:AutoZloboglaz821-@10.245.1.199
    Records a short video fragment for verification.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    from evileye.video_recorder.recording_params import RecordingParams
    
    # Camera details
    camera_url = "rtsp://user:AutoZloboglaz821-@10.245.1.199"
    username = "user"
    password = "AutoZloboglaz821-"
    
    cap = VideoCaptureGStreamer()
    
    # Enable recording to save video fragment
    recording_params = RecordingParams(
        enabled=True,
        container="mp4",
        segment_length_sec=300,
        retention_days=3,
        min_free_space_pct=80,
        min_file_size_kb=500,
        out_dir=str(tmp_path / "Recording"),
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
    
    # Verify parameters are set correctly
    assert cap.source_type == CaptureDeviceType.IpCamera, "Source type should be IpCamera"
    assert cap.source_address == camera_url, f"Source address should be {camera_url}"
    assert cap.username == username, f"Username should be {username}"
    assert cap.password == password, f"Password should be {password}"
    
    # Build pipeline string to verify it's correct
    pipeline_str = cap._build_pipeline()
    print(f"\n=== Pipeline String ===")
    print(pipeline_str)
    print(f"=======================\n")
    
    # Verify pipeline string contains expected elements
    # Note: We use simple pipeline like in api-refactoring (no protocols, rtpjitterbuffer, decodebin)
    assert "rtspsrc" in pipeline_str, "Pipeline should contain rtspsrc"
    assert "user-id" in pipeline_str, "Pipeline should contain user-id"
    assert "user-pw" in pipeline_str, "Pipeline should contain user-pw"
    assert "rtph265depay" in pipeline_str or "rtph264depay" in pipeline_str, "Pipeline should contain RTP depay"
    assert "videoconvert" in pipeline_str, "Pipeline should contain videoconvert"
    
    # Try to initialize (with timeout)
    print("Attempting to initialize GStreamer capture...")
    print("This may take up to 6 seconds...")
    
    import logging
    # Enable detailed logging for debugging
    logging.basicConfig(level=logging.DEBUG)
    cap.logger.setLevel(logging.DEBUG)
    
    init_result = cap.init()
    
    print(f"\nInit result: {init_result}")
    print(f"Is initialized: {cap.is_inited}")
    print(f"Is working: {cap.is_working}")
    
    if not init_result:
        print("\n=== Init Failed ===")
        print("Possible reasons:")
        print("1. Camera is not accessible")
        print("2. Network connectivity issues")
        print("3. RTSP authentication failed")
        print("4. GStreamer pipeline error")
        print("5. Codec not supported")
        print("6. Firewall blocking RTSP port")
        print("7. Camera requires different protocol (TCP vs UDP)")
        print("\nCheck logs above for detailed error messages.")
        
        # Check if we have last error stored
        if hasattr(cap, '_last_init_error') and cap._last_init_error:
            print(f"\nLast init error: {cap._last_init_error}")
        
        # Try to get more details from pipeline state
        if hasattr(cap, 'pipeline') and cap.pipeline:
            try:
                ret, state, pending = cap.pipeline.get_state(0)
                print(f"\nPipeline state: {state}")
                print(f"State change return: {ret}")
                print(f"Pending state: {pending}")
            except Exception as e:
                print(f"\nError getting pipeline state: {e}")
        
        # Suggest trying TCP protocol
        print("\n=== Suggestion ===")
        print("Try running the test with TCP protocol:")
        print("  cap._rtsp_protocol = 'tcp'")
        print("  before calling cap.init()")
    
    # Start capture to test reconnect logic
    if not cap.is_inited:
        print("\nStarting capture threads to test reconnect logic...")
        cap.start()
        
        # Wait a bit to see if reconnect happens
        print("Waiting 10 seconds to see if reconnect logic works...")
        time.sleep(10.0)
        
        print(f"After wait - Is initialized: {cap.is_inited}")
        print(f"After wait - Is working: {cap.is_working}")
        
        # Stop
        cap.stop()
    else:
        # If initialized, start and get a few frames
        print("\nCapture initialized successfully, testing frame capture...")
        cap.start()
        
        # Wait a bit for frames
        print("Waiting for frames...")
        time.sleep(3.0)
        
        # Try to get frames
        frames = cap.get()
        print(f"Frames received: {len(frames)}")
        
        if frames:
            frame = frames[0]
            print(f"Frame shape: {frame.image.shape if hasattr(frame, 'image') and frame.image is not None else 'None'}")
            print(f"Frame timestamp: {frame.time_stamp if hasattr(frame, 'time_stamp') else 'None'}")
        
        # Record for a few more seconds to get a video fragment
        print("Recording video fragment (5 seconds)...")
        time.sleep(5.0)
        
        cap.stop()
        cap.release()
        
        # Find recorded video files
        from pathlib import Path
        import datetime
        if hasattr(cap, 'recording_params') and cap.recording_params and cap.recording_params.enabled:
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
                    # Test functions should return None, not values
    
    # Note: This test may fail if camera is not accessible
    # It's primarily for debugging connection issues
    print("\n=== Test Complete ===")


def test_rtsp_pipeline_string_generation():
    """
    Test that pipeline string is generated correctly for RTSP camera.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    
    camera_url = "rtsp://user:AutoZloboglaz821-@10.245.1.199"
    username = "user"
    password = "AutoZloboglaz821-"
    
    cap = VideoCaptureGStreamer()
    cap.source_type = CaptureDeviceType.IpCamera
    cap.source_address = camera_url
    cap.username = username
    cap.password = password
    # Note: We use simple pipeline like in api-refactoring (no protocols parameter)
    # Test pipeline generation
    pipeline = cap._build_pipeline()
    print(f"\n=== Pipeline ===")
    print(pipeline)
    
    assert f"location={camera_url}" in pipeline, "Pipeline should contain camera URL"
    assert f"user-id={username}" in pipeline, "Pipeline should contain username"
    assert f"user-pw={password}" in pipeline, "Pipeline should contain password"
    
    # Verify pipeline has required elements
    # Note: We use simple pipeline like in api-refactoring (no extra parameters)
    assert "rtspsrc" in pipeline, "Pipeline should contain rtspsrc"
    assert "rtph265depay" in pipeline or "rtph264depay" in pipeline, "Pipeline should contain RTP depay"
    assert "videoconvert" in pipeline, "Pipeline should contain videoconvert"


def test_rtsp_connection_with_recording():
    """
    Test RTSP connection with recording enabled.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    from evileye.video_recorder.recording_params import RecordingParams
    from pathlib import Path
    import tempfile
    
    camera_url = "rtsp://user:AutoZloboglaz821-@10.245.1.199"
    username = "user"
    password = "AutoZloboglaz821-"
    
    cap = VideoCaptureGStreamer()
    
    # Create temporary directory for recording
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set recording parameters
        recording_params = RecordingParams(
            enabled=True,
            container="mp4",
            segment_length_sec=300,
            retention_days=3,
            min_free_space_pct=80,
            min_file_size_kb=500,
            out_dir=str(Path(tmpdir) / "Recording"),
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
    
    # Build pipeline - should include tee for recording
    pipeline_str = cap._build_pipeline()
    print(f"\n=== Pipeline with Recording ===")
    print(pipeline_str)
    
    # Verify recording branch is in pipeline
    assert "tee name=t" in pipeline_str, "Pipeline should contain tee for recording"
    assert "recording_queue" in pipeline_str, "Pipeline should contain recording_queue"
    
    # Verify appsink branch exists
    assert "appsink name=sink" in pipeline_str, "Pipeline should contain appsink"
    
    print("\nPipeline structure verified for recording")


def test_rtsp_gst_launch_command():
    """
    Generate gst-launch-1.0 command for manual testing.
    This helps debug connection issues by testing pipeline directly.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    
    camera_url = "rtsp://user:AutoZloboglaz821-@10.245.1.199"
    username = "user"
    password = "AutoZloboglaz821-"
    
    cap = VideoCaptureGStreamer()
    cap.set_params(
        source="IpCamera",
        camera=camera_url,
        source_ids=[0],
        source_names=["TestCam"],
        username=username,
        password=password,
    )
    
    # Test UDP
    cap._rtsp_protocol = 'udp'
    pipeline_udp = cap._build_pipeline()
    
    # Test TCP
    cap._rtsp_protocol = 'tcp'
    pipeline_tcp = cap._build_pipeline()
    
    print("\n" + "="*70)
    print("GST-LAUNCH-1.0 COMMANDS FOR MANUAL TESTING")
    print("="*70)
    
    print("\n--- UDP Protocol ---")
    print(f"gst-launch-1.0 {pipeline_udp}")
    
    print("\n--- TCP Protocol ---")
    print(f"gst-launch-1.0 {pipeline_tcp}")
    
    print("\n--- Simplified UDP (without appsink, just fakesink) ---")
    # Replace appsink with fakesink for testing
    simple_udp = pipeline_udp.replace("appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true", "fakesink")
    print(f"gst-launch-1.0 {simple_udp}")
    
    print("\n--- Simplified TCP (without appsink, just fakesink) ---")
    simple_tcp = pipeline_tcp.replace("appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true", "fakesink")
    print(f"gst-launch-1.0 {simple_tcp}")
    
    print("\n" + "="*70)
    print("Run these commands manually to test connection:")
    print("1. UDP: Copy the UDP command above and run in terminal")
    print("2. TCP: Copy the TCP command above and run in terminal")
    print("3. Check for error messages in the output")
    print("="*70 + "\n")
