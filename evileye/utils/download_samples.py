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
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from evileye.core.logger import get_module_logger

# Логгер модуля (конфигурация выполняется вызывающей стороной)
download_logger = get_module_logger("download_samples")

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


def _build_session() -> requests.Session:
    """Create a requests session with retries and connection pooling."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "EvilEye-Sample-Downloader/1.0"
    })
    return session


def download_file(url, filepath, description="", session: requests.Session | None = None, timeout: float = 30.0, chunk_size: int = 1024 * 1024):
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
        sess = session or _build_session()
        download_logger.info(f"Downloading {description}...")
        response = sess.get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=description, disable=(total_size == 0)) as pbar:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        
        return True
        
    except Exception as e:
        download_logger.info(f"Error downloading {description}: {e}")
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

def download_sample_videos(videos_dir="videos", force=False, parallel=True, max_workers: int | None = None):
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

    # Helper for single download
    def _task(name: str, info: dict, session: requests.Session):
        fp = videos_path / name
        if fp.exists() and not force:
            return name, {"status": "exists", "path": str(fp)}
        ok = download_file(info["url"], fp, info["description"], session=session)
        if ok and verify_file(fp, info.get("md5")):
            return name, {"status": "downloaded", "path": str(fp)}
        return name, {"status": "failed", "path": str(fp)}

    if parallel:
        workers = max_workers or min(4, len(SAMPLE_VIDEOS))
        session = _build_session()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_task, fn, info, session) for fn, info in SAMPLE_VIDEOS.items()]
            for fut in as_completed(futures):
                name, res = fut.result()
                results[name] = res
                download_logger.info(f"{name}: {res['status']}")
    else:
        session = _build_session()
        for filename, video_info in SAMPLE_VIDEOS.items():
            name, res = _task(filename, video_info, session)
            results[name] = res
            download_logger.info(f"{name}: {res['status']}")
    
    return results

def main():
    """Main function for command line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Download sample videos for EvilEye")
    parser.add_argument("--videos-dir", default="videos", help="Directory to save videos")
    parser.add_argument("--force", action="store_true", help="Force re-download existing files")
    
    args = parser.parse_args()
    
    download_logger.info("EvilEye Sample Videos Downloader")
    download_logger.info("=" * 40)
    
    results = download_sample_videos(args.videos_dir, args.force)
    
    download_logger.info("\nDownload Summary:")
    download_logger.info("-" * 20)
    
    for filename, result in results.items():
        download_logger.info(f"{filename}: {result['status']}")
    
    successful = sum(1 for r in results.values() if "downloaded" in r["status"] or r["status"] == "exists")
    total = len(results)
    
    download_logger.info(f"\nSuccessfully processed {successful}/{total} videos")
    
    if successful == total:
        download_logger.info("All sample videos are ready!")
        return 0
    else:
        download_logger.info("Some videos failed to download. Check your internet connection.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
