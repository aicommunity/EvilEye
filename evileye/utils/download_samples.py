#!/usr/bin/env python3
"""
Utility for downloading sample videos for EvilEye demonstrations.
"""

import os
import sys
import requests
from pathlib import Path
from tqdm import tqdm
import hashlib

# Sample video URLs (public domain or free to use)
SAMPLE_VIDEOS = {
    "planes_sample.mp4": {
        "url": "https://github.com/aicommunity/EvilEye/releases/download/dev/planes_sample.mp4",
        "description": "Single video sample with planes and without",
        "md5": None  # Placeholder MD5
    },
    "sample_split.mp4": {
        "url": "https://github.com/aicommunity/EvilEye/releases/download/dev/sample_split.mp4", 
        "description": "Sample with two head camera video for splitting to two sources",
        "md5": None  # Placeholder MD5
    },
    "6p-c0.avi": {
        "url": "https://github.com/aicommunity/EvilEye/releases/download/dev/6p-c0.avi",
        "description": "Video for testing multi-camera tracking (camera 0)", 
        "md5": None  # Placeholder MD5
    },
    "6p-c1.avi": {
        "url": "https://github.com/aicommunity/EvilEye/releases/download/dev/6p-c1.avi",
        "description": "Video for testing multi-camera tracking (camera 1)", 
        "md5": None  # Placeholder MD5
    }
}


def download_file(url, filepath, description=""):
    """
    Download a file with progress bar.
    
    Args:
        url: URL to download from
        filepath: Local path to save file
        description: Description for progress bar
        
    Returns:
        bool: True if download successful, False otherwise
    """
    try:
        print(f"Downloading {description}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=description) as pbar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        
        return True
        
    except Exception as e:
        print(f"Error downloading {description}: {e}")
        return False

def verify_file(filepath, expected_md5=None):
    """
    Verify downloaded file integrity (optional).
    
    Args:
        filepath: Path to file to verify
        expected_md5: Expected MD5 hash (optional)
        
    Returns:
        bool: True if file exists and MD5 matches (if provided)
    """
    if not os.path.exists(filepath):
        return False
    
    if expected_md5:
        with open(filepath, 'rb') as f:
            file_md5 = hashlib.md5(f.read()).hexdigest()
        return file_md5 == expected_md5
    
    return True

def download_sample_videos(videos_dir="videos", force=False):
    """
    Download sample videos for EvilEye demonstrations.
    
    Args:
        videos_dir: Directory to save videos
        force: Force re-download even if files exist
        
    Returns:
        dict: Status of each video download
    """
    videos_path = Path(videos_dir)
    videos_path.mkdir(exist_ok=True)
    
    results = {}
    
    for filename, video_info in SAMPLE_VIDEOS.items():
        filepath = videos_path / filename
        
        # Skip if file exists and not forcing re-download
        if filepath.exists() and not force:
            print(f"✓ {filename} already exists, skipping...")
            results[filename] = {"status": "exists", "path": str(filepath)}
            continue
        
        # Try primary URL first
        success = download_file(
            video_info["url"], 
            filepath, 
            video_info["description"]
        )
        
        if success and verify_file(filepath, video_info.get("md5")):
            results[filename] = {"status": "downloaded", "path": str(filepath)}
            print(f"✓ Successfully downloaded {filename}")
        else:
            results[filename] = {"status": "failed", "path": str(filepath)}
            print(f"✗ Failed to download {filename}")
    
    return results

def main():
    """Main function for command line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download sample videos for EvilEye")
    parser.add_argument("--videos-dir", default="videos", help="Directory to save videos")
    parser.add_argument("--force", action="store_true", help="Force re-download existing files")
    
    args = parser.parse_args()
    
    print("🎬 EvilEye Sample Videos Downloader")
    print("=" * 40)
    
    results = download_sample_videos(args.videos_dir, args.force)
    
    print("\n📊 Download Summary:")
    print("-" * 20)
    
    for filename, result in results.items():
        status_icon = "✓" if "downloaded" in result["status"] or result["status"] == "exists" else "✗"
        print(f"{status_icon} {filename}: {result['status']}")
    
    successful = sum(1 for r in results.values() if "downloaded" in r["status"] or r["status"] == "exists")
    total = len(results)
    
    print(f"\n✅ Successfully processed {successful}/{total} videos")
    
    if successful == total:
        print("🎉 All sample videos are ready!")
        return 0
    else:
        print("⚠️  Some videos failed to download. Check your internet connection.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
