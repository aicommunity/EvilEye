# VideoCaptureGStreamer Usage Guide

## Overview

`VideoCaptureGStreamer` is a GStreamer-based video capture class that provides enhanced performance and flexibility for various video sources compared to the OpenCV-based `VideoCaptureOpencv` class.

## Supported Source Types

### 1. IP Camera (RTSP Stream)

**Configuration:**
```json
{
  "camera": "rtsp://username:password@ip:port/path",
  "source": "IpCamera",
  "type": "VideoCaptureGStreamer",
  "username": "your_username",
  "password": "your_password",
  "desired_fps": 30
}
```

**GStreamer Pipeline:**
- With authentication: `rtspsrc location=rtsp://... userid=username passwd=password ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert`
- Without authentication: `rtspsrc location=rtsp://... ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert`

**Example URLs:**
- `rtsp://demo:demo@ipvmdemo.dyndns.org:5541/onvif-media/media.amp`
- `rtsp://192.168.1.100:554/stream1`
- `rtsp://user:pass@192.168.1.100:554/h264Preview_01_main`

### 2. USB Camera

**Configuration:**
```json
{
  "camera": "0",
  "source": "Device", 
  "type": "VideoCaptureGStreamer",
  "desired_fps": 30
}
```

**GStreamer Pipeline:**
- `v4l2src device=/dev/video0 ! videoconvert`

**Device IDs:**
- `"0"` - /dev/video0 (first USB camera)
- `"1"` - /dev/video1 (second USB camera)
- `"2"` - /dev/video2 (third USB camera)

### 3. Video File

**Configuration:**
```json
{
  "camera": "videos/sample.mp4",
  "source": "VideoFile",
  "type": "VideoCaptureGStreamer",
  "desired_fps": 30
}
```

**GStreamer Pipeline:**
- `filesrc location=videos/sample.mp4 ! decodebin ! videoconvert`

## Advantages of GStreamer Backend

### Performance Benefits
- **Hardware Acceleration**: Better utilization of GPU and hardware decoders
- **Lower CPU Usage**: More efficient video processing pipeline
- **Better Memory Management**: Optimized buffer handling
- **Real-time Processing**: Lower latency for live streams

### Format Support
- **H.264/H.265**: Native support for modern codecs
- **RTSP**: Optimized RTSP stream handling
- **Multiple Formats**: Support for various video containers and codecs
- **Hardware Decoding**: Automatic hardware decoder selection

### Network Optimization
- **TCP/UDP Protocols**: Configurable network protocols for RTSP
- **Buffer Management**: Optimized network buffer handling
- **Error Recovery**: Better handling of network interruptions

## Configuration Examples

Полные примеры конфигураций с GStreamer бэкендом доступны в папке `evileye/samples_configs/`:

### IP Camera with Authentication

**Пример конфигурации**: [ip_camera_gstreamer.json](../evileye/samples_configs/ip_camera_gstreamer.json)

Основные параметры:
- `source`: `"IpCamera"`
- `type`: `"VideoCaptureGStreamer"`
- `camera`: RTSP URL камеры
- `username` и `password`: Учетные данные для аутентификации (или используйте `credentials.json`)
- `desired_fps`: Желаемый FPS (опционально)

### USB Camera

**Пример конфигурации**: [usb_camera_gstreamer.json](../evileye/samples_configs/usb_camera_gstreamer.json)

Основные параметры:
- `source`: `"Device"`
- `type`: `"VideoCaptureGStreamer"`
- `camera`: Индекс устройства (обычно `"0"` для первой камеры)
- `desired_fps`: Желаемый FPS (опционально)

### Video File

**Пример конфигурации**: [single_video_gstreamer.json](../evileye/samples_configs/single_video_gstreamer.json)

Основные параметры:
- `source`: `"VideoFile"`
- `type`: `"VideoCaptureGStreamer"`
- `camera`: Путь к видео файлу
- `desired_fps`: Желаемый FPS (опционально)

Подробное описание всех параметров конфигурации см. в [Configuration Guide](CONFIGURATION_GUIDE.md).

## Troubleshooting

### Common Issues

1. **GStreamer Not Available**
   - Install GStreamer: `sudo apt-get install gstreamer1.0-tools gstreamer1.0-plugins-*`
   - Check Python bindings: `pip install PyGObject`

2. **RTSP Connection Failed**
   - Verify camera URL and credentials
   - Check network connectivity
   - Try different protocols (TCP/UDP)

3. **USB Camera Not Detected**
   - Check device exists: `ls /dev/video*`
   - Verify camera permissions
   - Try different device IDs (0, 1, 2, etc.)

4. **Performance Issues**
   - Reduce desired FPS
   - Check system resources
   - Enable hardware acceleration

### Debugging

Enable verbose logging to see GStreamer pipeline details:
```bash
evileye run configs/ip_camera_gstreamer.json --verbose
```

## Comparison with OpenCV Backend

| Feature | VideoCaptureOpencv | VideoCaptureGStreamer |
|---------|-------------------|----------------------|
| Performance | Good | Excellent |
| Hardware Acceleration | Limited | Full Support |
| RTSP Support | Basic | Advanced |
| Format Support | Limited | Extensive |
| Memory Usage | Higher | Lower |
| CPU Usage | Higher | Lower |
| Network Optimization | Basic | Advanced |

## Best Practices

1. **Use GStreamer for**:
   - IP cameras and RTSP streams
   - High-performance requirements
   - Hardware-accelerated processing
   - Network video sources

2. **Use OpenCV for**:
   - Simple video file processing
   - Basic camera access
   - Development and testing
   - Systems without GStreamer

3. **Configuration Tips**:
   - Set appropriate `desired_fps` for your use case
   - Use authentication for IP cameras
   - Test with different device IDs for USB cameras
   - Monitor system resources during processing

## Image Sequence Support

`VideoCaptureGStreamer` also supports reading image sequences from folders containing JPEG, PNG, or BMP files.

### Image Sequence Configuration
```json
{
  "camera": "images/sequence_%03d.jpg",
  "source": "ImageSequence",
  "type": "VideoCaptureGStreamer",
  "desired_fps": 10
}
```

### Supported Formats
- **JPEG**: `images/sequence_%03d.jpg`
- **PNG**: `images/frame_%04d.png`  
- **BMP**: `images/image_%05d.bmp`

### Use Cases
- Time-lapse photography processing
- Surveillance footage analysis
- Scientific image sequence processing
- Quality control and inspection

For detailed information, see [ImageSequence_GStreamer_Usage.md](ImageSequence_GStreamer_Usage.md).
