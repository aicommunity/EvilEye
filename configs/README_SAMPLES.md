# EvilEye Sample Configurations

This directory contains sample configurations for EvilEye system.

## Available Samples:

### 🎬 Video Processing
- **single_video.json** - Single video file processing (planes_sample.mp4)
- **single_video_split.json** - Single video with 2-way split processing (sample_split.mp4)
- **multi_videos.json** - Multiple video files with multi-camera tracking (6p-c0.avi, 6p-c1.avi)

### 📹 IP Camera Processing  
- **single_ip_camera.json** - Single IP camera stream processing

## Video Files:

The following video files are downloaded to `videos/` directory:
- **planes_sample.mp4** - Sample video with planes for single video processing
- **sample_split.mp4** - Video with two camera views for split processing
- **6p-c0.avi** - Multi-camera tracking video (camera 0)
- **6p-c1.avi** - Multi-camera tracking video (camera 1)

## Thread mode (no multiprocessing)

For the main poly setups, thread-mode copies use suffix `-thread.json`
(`execution_mode: thread` on sources, detectors, and trackers):

| Multiprocess (default) | Thread mode |
|------------------------|-------------|
| `poly-videos-gst.json` | `poly-videos-gst-thread.json` |
| `poly-videos.json` | `poly-videos-thread.json` |
| `poly-cameras-gstreamer.json` | `poly-cameras-gstreamer-thread.json` |
| `poly-cameras.json` | `poly-cameras-thread.json` |

PyCharm run configs: `process-poly-*-thread` in `.idea/runConfigurations/`.

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
