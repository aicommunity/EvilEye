"""
Memory monitor for EvilEye system.

Monitors memory usage in real-time, detects leaks, and automatically triggers cleanup.
"""

import os
import time
import gc
import threading
from typing import Optional, Dict, List, Tuple
from collections import deque
from datetime import datetime

try:
    import psutil
except ImportError:
    psutil = None
    print("WARNING: psutil not available, memory monitoring disabled")

from evileye.core.logger import get_module_logger


class MemoryMonitor:
    """Monitor memory usage and detect leaks in real-time."""
    
    def __init__(self, 
                 check_interval: float = 30.0,
                 leak_threshold_mb: float = 50.0,
                 leak_window_samples: int = 20,
                 auto_cleanup: bool = True):
        """
        Initialize memory monitor.
        
        Args:
            check_interval: Interval between memory checks in seconds
            leak_threshold_mb: Memory growth threshold in MB to detect leak
            leak_window_samples: Number of samples to consider for leak detection
            auto_cleanup: Whether to automatically trigger cleanup on leak detection
        """
        self.logger = get_module_logger("memory_monitor")
        self.check_interval = check_interval
        self.leak_threshold_mb = leak_threshold_mb
        self.leak_window_samples = leak_window_samples
        self.auto_cleanup = auto_cleanup
        
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.pid = os.getpid()
        
        # Memory samples: (timestamp, rss_mb, vms_mb)
        self.memory_samples: deque = deque(maxlen=100)
        
        # Statistics
        self.initial_rss_mb: Optional[float] = None
        self.peak_rss_mb: Optional[float] = None
        self.leak_detected_count = 0
        self.cleanup_triggered_count = 0
        
        # Callbacks for cleanup actions
        self.cleanup_callbacks: List[callable] = []
        
        if psutil is None:
            self.logger.warning("psutil not available, memory monitoring disabled")
    
    def add_cleanup_callback(self, callback: callable) -> None:
        """Add a callback function to be called during cleanup.
        
        Args:
            callback: Function to call during cleanup (should accept no arguments)
        """
        if callable(callback):
            self.cleanup_callbacks.append(callback)
            self.logger.debug(f"Added cleanup callback: {callback.__name__}")
    
    def get_memory_stats(self) -> Optional[Dict]:
        """Get current memory statistics.
        
        Returns:
            Dictionary with memory statistics or None if psutil unavailable
        """
        if psutil is None:
            return None
        
        try:
            process = psutil.Process(self.pid)
            mem_info = process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)
            vms_mb = mem_info.vms / (1024 * 1024)
            
            current_time = time.time()
            self.memory_samples.append((current_time, rss_mb, vms_mb))
            
            # Update statistics
            if self.initial_rss_mb is None:
                self.initial_rss_mb = rss_mb
            if self.peak_rss_mb is None or rss_mb > self.peak_rss_mb:
                self.peak_rss_mb = rss_mb
            
            # Detect leak
            leak_detected = False
            leak_growth_mb = 0.0
            leak_rate_mb_per_min = 0.0
            
            if len(self.memory_samples) >= self.leak_window_samples:
                recent = list(self.memory_samples)[-self.leak_window_samples:]
                first_rss = recent[0][1]
                last_rss = recent[-1][1]
                first_time = recent[0][0]
                last_time = recent[-1][0]
                
                growth = last_rss - first_rss
                time_diff = last_time - first_time
                
                if growth > self.leak_threshold_mb and time_diff > 0:
                    leak_detected = True
                    leak_growth_mb = growth
                    leak_rate_mb_per_min = (growth / time_diff) * 60.0
            
            return {
                'rss_mb': rss_mb,
                'vms_mb': vms_mb,
                'initial_rss_mb': self.initial_rss_mb,
                'peak_rss_mb': self.peak_rss_mb,
                'growth_mb': rss_mb - self.initial_rss_mb if self.initial_rss_mb else 0.0,
                'leak_detected': leak_detected,
                'leak_growth_mb': leak_growth_mb,
                'leak_rate_mb_per_min': leak_rate_mb_per_min,
                'samples_count': len(self.memory_samples)
            }
        except psutil.NoSuchProcess:
            self.logger.error(f"Process {self.pid} not found")
            return None
        except Exception as e:
            self.logger.error(f"Error getting memory stats: {e}", exc_info=True)
            return None
    
    def trigger_cleanup(self) -> None:
        """Trigger memory cleanup by calling callbacks and forcing GC."""
        self.logger.info("Triggering memory cleanup due to detected leak")
        self.cleanup_triggered_count += 1
        
        # Call registered cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                self.logger.error(f"Error in cleanup callback {callback.__name__}: {e}", exc_info=True)
        
        # Force garbage collection
        collected = gc.collect()
        self.logger.info(f"Memory cleanup completed: GC collected {collected} objects")
    
    def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        self.logger.info(f"Memory monitor started (PID={self.pid}, interval={self.check_interval}s)")
        
        while self.running:
            try:
                stats = self.get_memory_stats()
                if stats:
                    # Log memory statistics periodically
                    if len(self.memory_samples) % 10 == 0:  # Every 10 samples
                        leak_info = ""
                        if stats.get('leak_detected'):
                            leak_info = f", LEAK DETECTED: {stats.get('leak_growth_mb', 0):.1f}MB growth, {stats.get('leak_rate_mb_per_min', 0):.2f}MB/min"
                        self.logger.info(
                            f"Memory stats: RSS={stats['rss_mb']:.1f}MB, "
                            f"Growth={stats['growth_mb']:+.1f}MB, "
                            f"Peak={stats['peak_rss_mb']:.1f}MB{leak_info}"
                        )
                    
                    # Check for leak and trigger cleanup if needed
                    if stats['leak_detected']:
                        self.leak_detected_count += 1
                        self.logger.warning(
                            f"Memory leak detected: Growth={stats['leak_growth_mb']:.1f}MB "
                            f"over {self.leak_window_samples} samples "
                            f"(rate={stats['leak_rate_mb_per_min']:.2f}MB/min)"
                        )
                        
                        if self.auto_cleanup:
                            self.trigger_cleanup()
                
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Error in memory monitor loop: {e}", exc_info=True)
                time.sleep(self.check_interval)
        
        self.logger.info("Memory monitor stopped")
    
    def start(self) -> None:
        """Start memory monitoring in background thread."""
        if psutil is None:
            self.logger.warning("Cannot start memory monitor: psutil not available")
            return
        
        if self.running:
            self.logger.warning("Memory monitor already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="MemoryMonitor")
        self.monitor_thread.start()
        self.logger.info("Memory monitor started")
    
    def stop(self) -> None:
        """Stop memory monitoring."""
        if not self.running:
            return
        
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        
        # Print final statistics
        if self.memory_samples:
            final_stats = self.get_memory_stats()
            if final_stats:
                self.logger.info(
                    f"Memory monitor stopped. Final stats: "
                    f"RSS={final_stats['rss_mb']:.1f}MB, "
                    f"Total growth={final_stats['growth_mb']:+.1f}MB, "
                    f"Leaks detected={self.leak_detected_count}, "
                    f"Cleanups triggered={self.cleanup_triggered_count}"
                )
    
    def get_summary(self) -> Dict:
        """Get summary of memory monitoring.
        
        Returns:
            Dictionary with summary statistics
        """
        stats = self.get_memory_stats()
        return {
            'running': self.running,
            'initial_rss_mb': self.initial_rss_mb,
            'peak_rss_mb': self.peak_rss_mb,
            'current_stats': stats,
            'leak_detected_count': self.leak_detected_count,
            'cleanup_triggered_count': self.cleanup_triggered_count,
            'samples_count': len(self.memory_samples)
        }
