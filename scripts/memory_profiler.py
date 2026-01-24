#!/usr/bin/env python3
"""
Memory profiler for EvilEye system.

Monitors memory usage of a process using psutil and tracemalloc.
Detects memory leaks by tracking RSS memory growth over time.
"""

import os
import sys
import time
import argparse
import signal
from typing import Optional, List, Tuple
from datetime import datetime

try:
    import psutil
except ImportError:
    print("ERROR: psutil not installed. Install with: pip install psutil")
    sys.exit(1)

try:
    import tracemalloc
except ImportError:
    tracemalloc = None
    print("WARNING: tracemalloc not available (Python < 3.4)")


class MemoryProfiler:
    """Monitor memory usage of a process."""
    
    def __init__(self, pid: Optional[int] = None, interval: float = 5.0, 
                 leak_threshold_mb: float = 50.0, leak_window: int = 10):
        """
        Initialize memory profiler.
        
        Args:
            pid: Process ID to monitor (None = current process)
            interval: Sampling interval in seconds
            leak_threshold_mb: Memory growth threshold in MB to detect leak
            leak_window: Number of samples to consider for leak detection
        """
        self.pid = pid or os.getpid()
        self.interval = interval
        self.leak_threshold_mb = leak_threshold_mb
        self.leak_window = leak_window
        
        try:
            self.process = psutil.Process(self.pid)
        except psutil.NoSuchProcess:
            print(f"ERROR: Process {self.pid} not found")
            sys.exit(1)
        
        self.running = False
        self.samples: List[Tuple[float, float, float]] = []  # (time, rss_mb, vms_mb)
        self.tracemalloc_enabled = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        self.running = False
        print("\nStopping memory profiler...")
    
    def start_tracemalloc(self):
        """Start tracemalloc if available."""
        if tracemalloc is not None:
            tracemalloc.start()
            self.tracemalloc_enabled = True
            print("tracemalloc enabled")
        else:
            print("tracemalloc not available")
    
    def get_memory_stats(self) -> Tuple[float, float, Optional[dict]]:
        """
        Get current memory statistics.
        
        Returns:
            Tuple of (rss_mb, vms_mb, tracemalloc_stats)
        """
        try:
            mem_info = self.process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)
            vms_mb = mem_info.vms / (1024 * 1024)
        except psutil.NoSuchProcess:
            return 0.0, 0.0, None
        
        tracemalloc_stats = None
        if self.tracemalloc_enabled and tracemalloc is not None:
            try:
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc_stats = {
                    'current_mb': current / (1024 * 1024),
                    'peak_mb': peak / (1024 * 1024)
                }
            except Exception:
                pass
        
        return rss_mb, vms_mb, tracemalloc_stats
    
    def detect_leak(self) -> Optional[float]:
        """
        Detect memory leak based on recent samples.
        
        Returns:
            Memory growth rate in MB/s if leak detected, None otherwise
        """
        if len(self.samples) < self.leak_window:
            return None
        
        # Get recent samples
        recent = self.samples[-self.leak_window:]
        
        # Calculate memory growth
        first_rss = recent[0][1]
        last_rss = recent[-1][1]
        growth_mb = last_rss - first_rss
        
        if growth_mb > self.leak_threshold_mb:
            time_span = recent[-1][0] - recent[0][0]
            if time_span > 0:
                growth_rate = growth_mb / time_span
                return growth_rate
        
        return None
    
    def run(self, duration: Optional[float] = None):
        """
        Run memory profiler.
        
        Args:
            duration: Duration to run in seconds (None = run until interrupted)
        """
        self.running = True
        start_time = time.time()
        
        print(f"Monitoring process {self.pid}")
        print(f"Sampling interval: {self.interval}s")
        print(f"Leak threshold: {self.leak_threshold_mb} MB over {self.leak_window} samples")
        print("-" * 80)
        print(f"{'Time':<12} {'RSS (MB)':<12} {'VMS (MB)':<12} {'Growth':<12} {'Leak':<10}")
        if self.tracemalloc_enabled:
            print(f"{'Trace Current':<15} {'Trace Peak':<15}")
        print("-" * 80)
        
        initial_rss = None
        
        while self.running:
            rss_mb, vms_mb, tracemalloc_stats = self.get_memory_stats()
            current_time = time.time()
            elapsed = current_time - start_time
            
            if initial_rss is None:
                initial_rss = rss_mb
            
            growth_mb = rss_mb - initial_rss
            
            # Store sample
            self.samples.append((elapsed, rss_mb, vms_mb))
            
            # Detect leak
            leak_rate = self.detect_leak()
            leak_str = f"{leak_rate:.2f} MB/s" if leak_rate else "OK"
            
            # Print stats
            line = f"{elapsed:>10.1f}s {rss_mb:>10.2f} {vms_mb:>10.2f} {growth_mb:>+10.2f} {leak_str:<10}"
            if tracemalloc_stats:
                line += f" {tracemalloc_stats['current_mb']:>12.2f} {tracemalloc_stats['peak_mb']:>12.2f}"
            print(line)
            
            # Check duration
            if duration is not None and elapsed >= duration:
                break
            
            time.sleep(self.interval)
        
        # Print summary
        print("-" * 80)
        if self.samples:
            final_rss = self.samples[-1][1]
            total_growth = final_rss - initial_rss if initial_rss else 0
            print(f"\nSummary:")
            print(f"  Initial RSS: {initial_rss:.2f} MB")
            print(f"  Final RSS: {final_rss:.2f} MB")
            print(f"  Total growth: {total_growth:+.2f} MB")
            print(f"  Samples: {len(self.samples)}")
            
            if leak_rate:
                print(f"  WARNING: Memory leak detected! Growth rate: {leak_rate:.2f} MB/s")
            
            # Print top tracemalloc stats if available
            if self.tracemalloc_enabled and tracemalloc is not None:
                try:
                    snapshot = tracemalloc.take_snapshot()
                    top_stats = snapshot.statistics('lineno')
                    print(f"\nTop 10 memory allocations:")
                    for index, stat in enumerate(top_stats[:10], 1):
                        print(f"  {index}. {stat}")
                except Exception as e:
                    print(f"  Could not get tracemalloc stats: {e}")


def main():
    parser = argparse.ArgumentParser(description='Memory profiler for EvilEye')
    parser.add_argument('--pid', type=int, help='Process ID to monitor (default: current process)')
    parser.add_argument('--interval', type=float, default=5.0, help='Sampling interval in seconds (default: 5.0)')
    parser.add_argument('--duration', type=float, help='Duration to run in seconds (default: run until interrupted)')
    parser.add_argument('--leak-threshold', type=float, default=50.0, 
                       help='Memory growth threshold in MB to detect leak (default: 50.0)')
    parser.add_argument('--leak-window', type=int, default=10,
                       help='Number of samples to consider for leak detection (default: 10)')
    parser.add_argument('--tracemalloc', action='store_true', help='Enable tracemalloc tracking')
    
    args = parser.parse_args()
    
    profiler = MemoryProfiler(
        pid=args.pid,
        interval=args.interval,
        leak_threshold_mb=args.leak_threshold,
        leak_window=args.leak_window
    )
    
    if args.tracemalloc:
        profiler.start_tracemalloc()
    
    try:
        profiler.run(duration=args.duration)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
