# EvilEye `deploy-samples` Command

## Overview

The `evileye deploy-samples` command is designed to quickly set up a working EvilEye environment with pre-configured sample configurations and video files. This is the recommended starting point for new users who want to test the system without creating configurations from scratch.

## What It Does

The `deploy-samples` command performs the following steps:

1. **Runs regular deploy** - Creates `credentials.json` and `configs/` folder
2. **Creates videos directory** - Sets up `videos/` folder for sample videos
3. **Downloads sample videos** - Downloads 3 sample video files from public sources
4. **Copies sample configurations** - Deploys 4 pre-configured JSON configurations
5. **Creates documentation** - Generates `README_SAMPLES.md` with usage instructions

## Usage

```bash
evileye deploy-samples
```

## Sample Videos Downloaded

The command downloads the following sample videos to the `videos/` directory:

- **sample_video.mp4** - Big Buck Bunny (158MB, open source)
- **sample_video2.mp4** - Elephants Dream (16MB, open source)  
- **sample_video3.mp4** - For Bigger Blazes (6MB, open source)

These videos are downloaded from Google's public sample video repository and are free to use.

## Sample Configurations Created

The command creates the following configuration files in the `configs/` directory:

### 🎬 Video Processing Examples

#### 1. `single_video.json`
- **Purpose**: Single video file processing
- **Features**: Basic object detection and tracking
- **Video**: Uses `videos/sample_video.mp4`
- **GUI**: Single window display

#### 2. `single_video_split.json`
- **Purpose**: Single video with 4-way split processing
- **Features**: Video splitting into 4 quadrants with multi-camera tracking
- **Video**: Uses `videos/sample_video.mp4` split into 4 parts
- **GUI**: 2x2 grid display showing all splits

#### 3. `multi_videos.json`
- **Purpose**: Multiple video files with multi-camera tracking
- **Features**: Processes 3 different videos simultaneously
- **Videos**: Uses `videos/sample_video.mp4`, `sample_video2.mp4`, `sample_video3.mp4`
- **GUI**: 2x2 grid display (3 videos + empty slot)

### 📹 IP Camera Examples

#### 4. `single_ip_camera.json`
- **Purpose**: Single IP camera stream processing
- **Features**: Real-time IP camera feed processing
- **Camera**: Uses public demo RTSP stream
- **GUI**: Single window display

## Running Sample Configurations

After running `evileye deploy-samples`, you can immediately test the system:

```bash
# Test single video processing
evileye run configs/single_video.json

# Test video splitting
evileye run configs/single_video_split.json

# Test multiple videos
evileye run configs/multi_videos.json

# Test IP camera (requires internet connection)
evileye run configs/single_ip_camera.json
```

## Configuration Features

All sample configurations include:

- ✅ **Admin database credentials** - Ready for PostgreSQL setup
- ✅ **YOLO11n model** - Fast object detection
- ✅ **Botsort tracking** - Advanced object tracking
- ✅ **Multi-camera tracking** - Where appropriate
- ✅ **GUI visualization** - Real-time display
- ✅ **Database logging** - Object and event storage
- ✅ **Event detection** - Camera and zone events

## Customization

The sample configurations serve as templates. You can:

1. **Modify existing samples** - Edit the JSON files directly
2. **Create new configs** - Use `evileye-create` command
3. **Add your own videos** - Place videos in the `videos/` directory
4. **Configure your cameras** - Update IP camera URLs and credentials

## Troubleshooting

### Video Download Issues
If video downloads fail:
- Check your internet connection
- Videos will be skipped, but configs will still be created
- You can manually add videos to the `videos/` directory

### IP Camera Issues
If IP camera example fails:
- The demo stream may be unavailable
- Replace with your own camera URL in `credentials.json`
- Update the camera URL in `single_ip_camera.json`

### Database Issues
If database connection fails:
- Ensure PostgreSQL is running
- Update database credentials in `credentials.json`
- Check that the database exists or can be created

## File Structure After Deployment

```
your_project/
├── credentials.json          # Database and camera credentials
├── videos/                   # Sample video files
│   ├── sample_video.mp4      # Big Buck Bunny
│   ├── sample_video2.mp4     # Elephants Dream
│   └── sample_video3.mp4     # For Bigger Blazes
└── configs/                  # Configuration files directory
    ├── single_video.json     # Single video processing
    ├── single_video_split.json # Video with 4-way split
    ├── multi_videos.json     # Multiple videos with tracking
    ├── single_ip_camera.json # IP camera processing
    └── README_SAMPLES.md     # This guide
```

## Next Steps

After successfully running sample configurations:

1. **Explore the GUI** - Try different visualization options
2. **Check the database** - View stored objects and events
3. **Modify configurations** - Adjust detection parameters
4. **Add your own sources** - Configure your cameras or videos
5. **Create custom configs** - Use `evileye-create` for your use cases

## Support

If you encounter issues with the sample configurations:

1. Check the main README.md for general troubleshooting
2. Verify that all dependencies are installed
3. Ensure PostgreSQL is properly configured
4. Check that video files are accessible
5. Review the configuration JSON files for syntax errors

The sample configurations are designed to work out-of-the-box and provide a solid foundation for understanding and extending the EvilEye system.



