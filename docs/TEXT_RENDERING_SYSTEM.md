# EvilEye Text Rendering System

## Overview

The EvilEye Text Rendering System provides adaptive text positioning and sizing capabilities for drawing text on images. It allows specifying font sizes in points (pt) and positions in percentages of image size, making text rendering resolution-independent and easily configurable.

## Key Features

### **Resolution Independence**
- Font sizes specified in points (pt) instead of pixels
- Positions specified as percentages of image dimensions
- Automatic scaling for different image resolutions

### **Flexible Positioning**
- Absolute positioning using percentages
- Relative positioning near bounding boxes
- Automatic boundary checking and adjustment

### **Rich Styling**
- Configurable font faces, colors, and thickness
- Optional background colors with padding
- Auto-calculated thickness based on font size

### **Easy Configuration**
- JSON-based configuration in pipeline configs
- Default values with override capability
- Backward compatibility with existing code

## Core Functions

### `put_text_adaptive(image, text, position_percent, **kwargs)`

Draws text at a specific percentage position on the image.

**Parameters:**
- `image`: OpenCV image
- `text`: Text string to draw
- `position_percent`: Tuple (x_percent, y_percent) from top-left
- `font_size_pt`: Font size in points (default: 12)
- `font_face`: OpenCV font face (default: cv2.FONT_HERSHEY_SIMPLEX)
- `color`: Text color as BGR tuple (default: white)
- `thickness`: Font thickness (auto-calculated if None)
- `background_color`: Background color (optional)
- `padding_percent`: Padding around text in percent

**Example:**
```python
# Draw text at 10% from left, 20% from top
put_text_adaptive(image, "Hello World", (10, 20), 
                 font_size_pt=16, color=(255, 255, 255))
```

### `put_text_with_bbox(image, text, bbox, **kwargs)`

Draws text near a bounding box with adaptive positioning.

**Parameters:**
- `image`: OpenCV image
- `text`: Text string to draw
- `bbox`: Bounding box (x1, y1, x2, y2)
- `position_offset_percent`: Offset from bbox in percent
- Other parameters same as `put_text_adaptive`

**Example:**
```python
# Draw text above bounding box
put_text_with_bbox(image, "Object 1", bbox, 
                  font_size_pt=12, position_offset_percent=(0, -10))
```

### `pt_to_pixels(pt_size, dpi=96)`

Converts font size from points to pixels.

**Parameters:**
- `pt_size`: Font size in points
- `dpi`: Dots per inch (default: 96 for standard screen)

**Returns:**
- Font size in pixels

### `percent_to_pixels(percent, total_size)`

Converts percentage to pixels.

**Parameters:**
- `percent`: Percentage value (0.0 to 100.0)
- `total_size`: Total size in pixels

**Returns:**
- Position in pixels

## Configuration

### Text Configuration in JSON

Секция `text_config` размещается внутри секции `visualizer` в конфигурационном файле. Примеры полных конфигураций с `text_config`:

- [single_video.json](../evileye/samples_configs/single_video.json)
- [single_ip_camera.json](../evileye/samples_configs/single_ip_camera.json)
- [multi_videos.json](../evileye/samples_configs/multi_videos.json)

**Базовая структура**:

```json
{
  "visualizer": {
    "text_config": {
      "font_size_pt": 14,
      "font_face": 0,
      "color": [255, 255, 255],
      "thickness": null,
      "background_color": [0, 0, 0],
      "padding_percent": 1.5,
      "position_offset_percent": [0, -8]
    }
  }
}
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `font_size_pt` | int | 12 | Font size in points |
| `font_face` | int | 0 | OpenCV font face constant |
| `color` | [int, int, int] | [255, 255, 255] | Text color (BGR) |
| `thickness` | int/null | null | Font thickness (auto if null) |
| `background_color` | [int, int, int]/null | null | Background color (BGR) |
| `padding_percent` | float | 2.0 | Padding around text in percent |
| `position_offset_percent` | [float, float] | [0, -10] | Offset from bbox in percent |

### Font Face Constants

| Value | Constant | Description |
|-------|----------|-------------|
| 0 | cv2.FONT_HERSHEY_SIMPLEX | Normal sans-serif |
| 1 | cv2.FONT_HERSHEY_PLAIN | Small sans-serif |
| 2 | cv2.FONT_HERSHEY_DUPLEX | Normal sans-serif (thicker) |
| 3 | cv2.FONT_HERSHEY_COMPLEX | Normal serif |
| 4 | cv2.FONT_HERSHEY_TRIPLEX | Normal serif (thicker) |
| 5 | cv2.FONT_HERSHEY_COMPLEX_SMALL | Smaller serif |
| 6 | cv2.FONT_HERSHEY_SCRIPT_SIMPLEX | Handwriting style |
| 7 | cv2.FONT_HERSHEY_SCRIPT_COMPLEX | Handwriting style (thicker) |

## Usage Examples

### Basic Text Drawing

```python
from evileye.utils.utils import put_text_adaptive

# Draw text at specific position
put_text_adaptive(image, "Camera 1", (10, 10), 
                 font_size_pt=16, color=(255, 255, 255))

# Draw text with background
put_text_adaptive(image, "Recording", (90, 10), 
                 font_size_pt=14, color=(255, 255, 255),
                 background_color=(0, 0, 0))
```

### Object Labeling

```python
from evileye.utils.utils import put_text_with_bbox

# Draw object labels
for obj in detected_objects:
    bbox = obj['bbox']
    label = f"{obj['class']} {obj['confidence']:.2f}"
    
    put_text_with_bbox(image, label, bbox,
                      font_size_pt=12, color=(255, 255, 255),
                      background_color=(0, 0, 0))
```

### Configuration-Based Rendering

```python
from evileye.utils.utils import apply_text_config, put_text_adaptive

# Get text configuration from pipeline config
text_config = pipeline_config.get('text_config', {})

# Apply configuration with defaults
config = apply_text_config(text_config)

# Use configuration for text rendering
put_text_adaptive(image, "Status", (50, 50), **config)
```

## Integration with Existing Code

### Updated Functions

The following functions have been updated to support the new text rendering system:

1. **`draw_boxes()`** - Now accepts `text_config` parameter
2. **`draw_boxes_tracking()`** - Now accepts `text_config` parameter

### Backward Compatibility

All existing code continues to work without changes. The new text configuration is optional and uses sensible defaults when not provided.

## Sample Configurations

Все примеры конфигураций в `evileye/samples_configs/` содержат секцию `text_config` в разделе `visualizer`. Примеры:

- **Базовый пример**: [single_video.json](../evileye/samples_configs/single_video.json) - содержит `text_config` с font_size_pt: 42
- **Несколько видео**: [multi_videos.json](../evileye/samples_configs/multi_videos.json) - настройки для мультикамерного отображения
- **IP камера**: [single_ip_camera.json](../evileye/samples_configs/single_ip_camera.json) - пример для IP камеры

Подробное описание всех параметров `text_config` см. в [Configuration Guide](CONFIGURATION_GUIDE.md#секция-visualizer).

### Примеры секции text_config

#### High-Resolution Display (4K)
```json
{
  "text_config": {
    "font_size_pt": 20,
    "color": [255, 255, 255],
    "background_color": [0, 0, 0],
    "padding_percent": 2.0,
    "position_offset_percent": [0, -12]
  }
}
```

#### Small Display (VGA)
```json
{
  "text_config": {
    "font_size_pt": 8,
    "color": [255, 255, 255],
    "background_color": [0, 0, 0],
    "padding_percent": 1.0,
    "position_offset_percent": [0, -5]
  }
}
```

#### Multi-Camera Setup
```json
{
  "text_config": {
    "font_size_pt": 10,
    "color": [255, 255, 255],
    "background_color": [0, 0, 0],
    "padding_percent": 0.8,
    "position_offset_percent": [0, -6]
  }
}
```

## Testing

Run the test script to verify the system:

```bash
python test_text_rendering.py
```

This will generate test images showing:
- Different resolutions (VGA to 4K)
- Various font sizes
- Different positioning scenarios
- Edge cases and error handling

## Performance Considerations

### Optimization Tips

1. **Reuse Configurations**: Apply text configuration once and reuse
2. **Batch Operations**: Group text drawing operations when possible
3. **Font Face Selection**: Use simpler fonts for better performance
4. **Background Colors**: Only use when necessary for readability

### Memory Usage

- Text rendering is lightweight and doesn't significantly impact memory
- Font size calculations are cached internally
- No additional memory allocation for configuration objects

## Troubleshooting

### Common Issues

1. **Text Too Small/Large**
   - Adjust `font_size_pt` in configuration
   - Check DPI settings if using custom displays

2. **Text Positioned Incorrectly**
   - Verify percentage values (0-100)
   - Check `position_offset_percent` for bbox text

3. **Text Not Visible**
   - Ensure color contrast with background
   - Add `background_color` for better visibility
   - Check if text is outside image bounds

4. **Performance Issues**
   - Reduce font size for large amounts of text
   - Use simpler font faces
   - Consider disabling background colors

### Debug Mode

Enable debug output by setting environment variable:
```bash
export EVILEYE_TEXT_DEBUG=1
```

This will print detailed information about text positioning and sizing calculations.

## Future Enhancements

### Planned Features

1. **Multi-line Text Support**
2. **Text Alignment Options**
3. **Custom Font Loading**
4. **Animation Support**
5. **Internationalization (Unicode)**

### Contributing

When adding new text rendering features:

1. Follow the existing function naming conventions
2. Include comprehensive docstrings
3. Add unit tests for new functions
4. Update this documentation
5. Ensure backward compatibility

## Conclusion

The EvilEye Text Rendering System provides a robust, flexible, and easy-to-use solution for text rendering in computer vision applications. It eliminates the need for manual pixel calculations and provides consistent text appearance across different resolutions and display sizes.



