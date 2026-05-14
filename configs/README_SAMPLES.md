# EvilEye Sample Configurations

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
