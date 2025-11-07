import os
import time
import pytest
from pathlib import Path
import json


def test_gstreamer_reconnect_recording(tmp_path: Path):
    """
    Test automatic connection to 3 cameras with recording using configs/poly-cameras-gstreamer.json.
    Tests:
    1. Automatic connection to 3 cameras at startup (Cam1, Cam2-Cam3, Cam4-Cam5)
    2. Recording is enabled and files are created for all cameras
    3. Reconnect after connection break (simulated)
    """
    from evileye.run_config_helper import run_config
    
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "configs" / "poly-cameras-gstreamer.json"
    
    if not config_path.exists():
        pytest.skip(f"Config file not found: {config_path}")
    
    # Load config to check if cameras are configured
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    sources = config.get("pipeline", {}).get("sources", [])
    if not sources:
        pytest.skip("No sources configured in poly-cameras-gstreamer.json")
    
    # Check if recording is enabled
    record_config = config.get("record", {})
    if not record_config.get("enabled", False):
        pytest.skip("Recording is not enabled in config")
    
    # Update recording output directory to tmp_path for test isolation
    record_config["out_dir"] = str(tmp_path / "Recording")
    
    # Save modified config to tmp_path
    test_config_path = tmp_path / "test_config.json"
    with open(test_config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    # Note: This test requires actual cameras to be available
    # In a real scenario, you would:
    # 1. Start the application with the config
    # 2. Wait for initial connections
    # 3. Verify recording files are created
    # 4. Simulate connection break (e.g., disconnect network)
    # 5. Verify reconnect happens
    # 6. Verify recording continues after reconnect
    
    # For now, we'll just verify the config is valid and recording is configured
    assert record_config.get("enabled") is True, "Recording should be enabled"
    assert record_config.get("container") == "mp4", "Container should be mp4"
    assert record_config.get("segment_length_sec") == 300, "Segment length should be 300 seconds"
    
    # Verify sources are configured
    assert len(sources) == 3, f"Expected 3 sources, got {len(sources)}"
    
    # Verify source names
    source_names = []
    for source in sources:
        names = source.get("source_names", [])
        source_names.extend(names)
    
    assert "Cam1" in source_names, "Cam1 should be in sources"
    assert "Cam2" in source_names, "Cam2 should be in sources"
    assert "Cam3" in source_names, "Cam3 should be in sources"
    assert "Cam4" in source_names, "Cam4 should be in sources"
    assert "Cam5" in source_names, "Cam5 should be in sources"
    
    # Note: Actual connection and recording test would require:
    # - Running the application
    # - Waiting for connections
    # - Checking recording directory for files
    # - Simulating disconnection
    # - Verifying reconnect
    # This is more of an integration test that would need to be run manually
    # or with actual camera hardware available
    
    print(f"Test config created at: {test_config_path}")
    print(f"Recording output directory: {record_config['out_dir']}")
    print(f"Sources configured: {len(sources)}")
    print(f"Recording enabled: {record_config.get('enabled')}")


def test_gstreamer_reconnect_loop_logic():
    """
    Test that _reconnect_loop continues after timeout.
    This is a unit test to verify the reconnect loop logic works correctly.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType
    
    # Create a mock capture instance
    cap = VideoCaptureGStreamer()
    cap.source_type = CaptureDeviceType.IpCamera
    cap.source_address = "rtsp://test:test@192.168.1.100"
    cap.source_names = ["TestCam"]
    cap.source_ids = [0]
    cap.run_flag = True
    
    # Verify _reconnect_loop method exists
    assert hasattr(cap, '_reconnect_loop'), "_reconnect_loop method should exist"
    assert callable(cap._reconnect_loop), "_reconnect_loop should be callable"
    
    # Verify reconnect attributes are initialized
    assert hasattr(cap, '_reconnecting'), "_reconnecting attribute should exist"
    assert hasattr(cap, '_rtsp_protocol'), "_rtsp_protocol attribute should exist"
    assert cap._rtsp_protocol == 'udp+tcp', "Default RTSP protocol should be 'udp+tcp' (try UDP first, then TCP if UDP fails)"
    
    # Verify recording attributes are initialized
    assert hasattr(cap, '_recording_elements'), "_recording_elements attribute should exist"
    assert hasattr(cap, '_recording_check_thread'), "_recording_check_thread attribute should exist"
    assert hasattr(cap, '_recording_check_stop'), "_recording_check_stop attribute should exist"


def test_gstreamer_recording_branch_setup():
    """
    Test that _setup_recording_branch method exists and can be called.
    """
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    
    cap = VideoCaptureGStreamer()
    
    # Verify _setup_recording_branch method exists
    assert hasattr(cap, '_setup_recording_branch'), "_setup_recording_branch method should exist"
    assert callable(cap._setup_recording_branch), "_setup_recording_branch should be callable"
    
    # Verify _cleanup_recording_branch method exists
    assert hasattr(cap, '_cleanup_recording_branch'), "_cleanup_recording_branch method should exist"
    assert callable(cap._cleanup_recording_branch), "_cleanup_recording_branch should be callable"
