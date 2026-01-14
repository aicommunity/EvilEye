# Image Sequence Processing with GStreamer

## Overview

`VideoCaptureGStreamer` now supports reading image sequences from folders containing JPEG, PNG, or BMP files. This is useful for processing time-lapse photography, surveillance footage, or any sequence of images.

## Supported Formats

- **JPEG** (.jpg, .jpeg)
- **PNG** (.png) 
- **BMP** (.bmp)

## Configuration

### Basic Image Sequence (with file pattern)
```json
{
  "camera": "images/sequence_%03d.jpg",
  "source": "ImageSequence",
  "type": "VideoCaptureGStreamer",
  "desired_fps": 10
}
```

### All Images in Folder (no file pattern)
```json
{
  "camera": "images/",
  "source": "ImageSequence",
  "type": "VideoCaptureGStreamer",
  "desired_fps": 10
}
```


## File Naming Patterns

GStreamer's `multifilesrc` supports various naming patterns:

### Sequential Numbering
- `image_001.jpg`, `image_002.jpg`, `image_003.jpg` → `"images/image_%03d.jpg"`
- `frame_0001.png`, `frame_0002.png` → `"images/frame_%04d.png"`
- `photo_00001.bmp`, `photo_00002.bmp` → `"images/photo_%05d.bmp"`

### Pattern Format
- `%03d` - 3-digit zero-padded numbers (001, 002, 003...)
- `%04d` - 4-digit zero-padded numbers (0001, 0002, 0003...)
- `%05d` - 5-digit zero-padded numbers (00001, 00002, 00003...)

## Directory Structure Examples

```
images/
├── sequence_001.jpg
├── sequence_002.jpg
├── sequence_003.jpg
└── sequence_004.jpg
```

```
frames/
├── frame_0001.png
├── frame_0002.png
├── frame_0003.png
└── frame_0004.png
```

## GStreamer Pipeline

### File Pattern Pipeline
The image sequence pipeline with file pattern uses:
```
multifilesrc location=images/sequence_%03d.jpg ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink
```

### Folder Pipeline
The image folder pipeline (all images) uses:
```
multifilesrc location=images/* ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink
```

## Configuration Examples

### Complete Configuration for JPEG Sequence
```json
{
  "pipeline": {
    "pipeline_class": "PipelineSurveillance",
    "sources": [
      {
        "camera": "images/sequence_%03d.jpg",
        "source": "ImageSequence",
        "type": "VideoCaptureGStreamer",
        "split": false,
        "num_split": 0,
        "src_coords": [0],
        "source_ids": [0],
        "source_names": ["Image Sequence"],
        "desired_fps": 10
      }
    ],
    "detectors": [
      {
        "model": "models/yolo11n.pt",
        "classes": [0, 1, 24, 25, 63, 66, 67],
        "source_ids": [0],
        "roi": [[]],
        "type": "ObjectDetectorRtdetr"
      }
    ],
    "trackers": [
      {
        "type": "ObjectTrackingBotsort",
        "source_ids": [0]
      }
    ],
    "handlers": [
      {
        "type": "ObjectsHandler",
        "source_ids": [0]
      }
    ],
    "visualizers": [
      {
        "type": "BoundingBoxVisualizer",
        "source_ids": [0]
      }
    ],
    "display": {
      "type": "display",
      "source_ids": [0]
    }
  }
}
```

## Usage Examples

### 1. Time-lapse Photography
```bash
# Process time-lapse images
evileye run configs/image_sequence_gstreamer_jpg.json
```

### 2. All Images in Folder
```bash
# Process all images in folder (mixed formats)
evileye run configs/image_sequence_gstreamer_folder.json
```


## Performance Considerations

### Frame Rate
- Set appropriate `desired_fps` for your use case
- Lower FPS for time-lapse sequences
- Higher FPS for surveillance footage

### Memory Usage
- Image sequences can be memory-intensive
- Consider image resolution and sequence length
- Monitor system resources during processing

### File Organization
- Ensure consistent naming convention
- Use zero-padded numbering
- Keep images in dedicated folders

## Troubleshooting

### Common Issues

1. **No Images Found**
   - Check file naming pattern
   - Verify directory path
   - Ensure images exist

2. **Wrong Frame Order**
   - Use zero-padded numbering
   - Check pattern format (e.g., %03d vs %3d)

3. **Performance Issues**
   - Reduce image resolution
   - Lower desired FPS
   - Check disk I/O performance

### Debugging

Enable verbose logging:
```bash
evileye run configs/image_sequence_gstreamer.json --verbose
```

Check GStreamer pipeline:
```bash
gst-launch-1.0 multifilesrc location=images/sequence_%03d.jpg ! decodebin ! videoconvert ! autovideosink
```

## Advantages of GStreamer for Image Sequences

### Performance Benefits
- **Efficient Decoding**: Hardware-accelerated image decoding
- **Memory Optimization**: Better memory management for large sequences
- **Format Support**: Native support for multiple image formats
- **Pipeline Optimization**: Optimized processing pipeline

### Format Support
- **JPEG**: Full JPEG support with hardware acceleration
- **PNG**: Efficient PNG decoding
- **BMP**: Native BMP support
- **Other Formats**: Support for additional formats through plugins

## Best Practices

1. **File Naming**
   - Use consistent zero-padded numbering
   - Choose appropriate padding (3-5 digits)
   - Avoid gaps in numbering

2. **Directory Structure**
   - Keep images in dedicated folders
   - Use descriptive folder names
   - Organize by date/time if needed

3. **Performance**
   - Optimize image resolution for your use case
   - Consider compression vs quality trade-offs
   - Monitor system resources

4. **Configuration**
   - Set appropriate frame rates
   - Choose suitable detection models
   - Configure tracking parameters

## Comparison with Video Files

| Feature | Video Files | Image Sequences |
|---------|-------------|-----------------|
| Storage | Compressed | Uncompressed |
| Quality | Variable | High |
| Processing | Fast | Moderate |
| Flexibility | Limited | High |
| Storage Space | Lower | Higher |
| Quality Control | Limited | Full |

## Use Cases

1. **Surveillance Systems**
   - High-quality surveillance footage
   - Frame-by-frame analysis
   - Evidence preservation

2. **Scientific Research**
   - Microscopy images
   - Astronomical observations
   - Medical imaging

3. **Time-lapse Photography**
   - Construction monitoring
   - Weather observations
   - Growth studies

4. **Quality Control**
   - Manufacturing inspection
   - Product quality assessment
   - Defect detection
