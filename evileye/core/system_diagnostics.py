"""
System diagnostics and automatic issue fixing for EvilEye.

Monitors system state, detects issues, and automatically fixes common problems.
"""

import re
import time
import gc
import threading
from typing import Optional, Dict, List, Any, Callable
from collections import deque, defaultdict
from datetime import datetime
from pathlib import Path

from evileye.core.logger import get_module_logger
from evileye.core.memory_monitor import MemoryMonitor


class SystemDiagnostics:
    """Automatic system diagnostics and issue fixing."""
    
    # Error patterns to detect in logs
    ERROR_PATTERNS = {
        'no_frames': re.compile(r'Pipeline PLAYING but no frames received after \d+s'),
        'none_image': re.compile(r'Received None image|All images are None'),
        'processing_error': re.compile(r'Error processing frame|Failed to extract frame data'),
        'loop_restart_failed': re.compile(r'Loop restart failed'),
        'attribute_error': re.compile(r'AttributeError.*clear|AttributeError.*Queue'),
        'pre_event_frames': re.compile(r'No pre-event frames found'),
        'split_stream_empty': re.compile(r'Split stream returned empty capture_images'),
    }
    
    def __init__(self, 
                 log_file: Optional[str] = None,
                 check_interval: float = 30.0,
                 auto_fix: bool = True):
        """
        Initialize system diagnostics.
        
        Args:
            log_file: Path to log file to monitor (None = monitor from logger)
            check_interval: Interval between diagnostic checks in seconds
            auto_fix: Whether to automatically fix detected issues
        """
        self.logger = get_module_logger("system_diagnostics")
        self.log_file = log_file
        self.check_interval = check_interval
        self.auto_fix = auto_fix
        
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Issue tracking
        self.detected_issues: deque = deque(maxlen=100)
        self.fixes_applied: deque = deque(maxlen=100)
        self.verification_results: deque = deque(maxlen=100)
        
        # Issue counters by type
        self.issue_counts: Dict[str, int] = defaultdict(int)
        
        # Last log position for file monitoring
        self.last_log_position = 0
        
        # Memory monitor integration
        self.memory_monitor: Optional[MemoryMonitor] = None
        
        # Callbacks for accessing system components
        self.pipeline_getter: Optional[Callable] = None
        self.event_buffer_getter: Optional[Callable] = None
        
        # Statistics
        self.last_check_time: Optional[float] = None
        self.total_checks = 0
        self.total_issues_detected = 0
        self.total_fixes_applied = 0
    
    def set_pipeline_getter(self, getter: Callable) -> None:
        """Set callback to get pipeline instance.
        
        Args:
            getter: Function that returns pipeline instance
        """
        self.pipeline_getter = getter
        self.logger.debug("Pipeline getter callback set")
    
    def set_event_buffer_getter(self, getter: Callable) -> None:
        """Set callback to get event buffer instances.
        
        Args:
            getter: Function that returns dict of {source_id: EventBuffer}
        """
        self.event_buffer_getter = getter
        self.logger.debug("Event buffer getter callback set")
    
    def set_memory_monitor(self, monitor: MemoryMonitor) -> None:
        """Set memory monitor instance.
        
        Args:
            monitor: MemoryMonitor instance
        """
        self.memory_monitor = monitor
        self.logger.debug("Memory monitor set")
    
    def monitor_logs(self) -> List[Dict]:
        """
        Monitor logs for issues.
        
        Returns:
            List of detected issues
        """
        issues = []
        
        if not self.log_file or not Path(self.log_file).exists():
            return issues
        
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Seek to last position
                f.seek(self.last_log_position)
                
                # Read new lines
                new_lines = f.readlines()
                self.last_log_position = f.tell()
                
                # Check each line for error patterns
                for line in new_lines:
                    for issue_type, pattern in self.ERROR_PATTERNS.items():
                        if pattern.search(line):
                            issue = {
                                'type': issue_type,
                                'line': line.strip(),
                                'timestamp': datetime.now().isoformat(),
                                'pattern_match': pattern.search(line).group(0) if pattern.search(line) else None
                            }
                            issues.append(issue)
                            self.issue_counts[issue_type] += 1
                            self.total_issues_detected += 1
                            
                            # Extract source names if present
                            source_match = re.search(r"for (\[.*?\]|'.*?')", line)
                            if source_match:
                                issue['source'] = source_match.group(1)
                            
                            break  # Only match first pattern per line
        except Exception as e:
            self.logger.error(f"Error monitoring logs: {e}", exc_info=True)
        
        # Store detected issues
        for issue in issues:
            self.detected_issues.append(issue)
        
        return issues
    
    def diagnose_system_state(self) -> Dict:
        """
        Diagnose current system state.
        
        Returns:
            Dictionary with diagnosis results
        """
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'issues': [],
            'memory_stats': None,
            'capture_status': {},
            'event_buffer_status': {}
        }
        
        # Check logs for issues
        log_issues = self.monitor_logs()
        diagnosis['issues'].extend(log_issues)
        
        # Check memory
        if self.memory_monitor:
            memory_stats = self.memory_monitor.get_memory_stats()
            if memory_stats:
                diagnosis['memory_stats'] = memory_stats
                if memory_stats.get('leak_detected'):
                    diagnosis['issues'].append({
                        'type': 'memory_leak',
                        'growth_mb': memory_stats.get('leak_growth_mb', 0),
                        'rate_mb_per_min': memory_stats.get('leak_rate_mb_per_min', 0),
                        'timestamp': datetime.now().isoformat()
                    })
        
        # Check capture status
        if self.pipeline_getter:
            try:
                pipeline = self.pipeline_getter()
                if pipeline and hasattr(pipeline, 'processors'):
                    for processor in pipeline.processors:
                        if processor and hasattr(processor, 'get_processors'):
                            # ProcessorSource contains VideoCapture instances
                            for proc in processor.get_processors():
                                if proc and hasattr(proc, 'is_working'):
                                    source_names = getattr(proc, 'source_names', ['Unknown'])
                                    # is_working is a method that returns bool, call it
                                    try:
                                        is_working = proc.is_working() if callable(proc.is_working) else proc.is_working
                                    except (TypeError, AttributeError):
                                        # Fallback: try to get as attribute
                                        is_working = getattr(proc, 'is_working', False)
                                    is_inited = getattr(proc, 'is_inited', False)
                                    
                                    diagnosis['capture_status'][str(source_names)] = {
                                        'is_working': is_working,
                                        'is_inited': is_inited,
                                        'source_type': getattr(proc, 'source_type', None)
                                    }
                                    
                                    # Detect issues
                                    if not is_working and is_inited:
                                        diagnosis['issues'].append({
                                            'type': 'capture_not_working',
                                            'source': str(source_names),
                                            'timestamp': datetime.now().isoformat()
                                        })
            except Exception as e:
                self.logger.error(f"Error checking capture status: {e}", exc_info=True)
        
        # Check event buffer status
        if self.event_buffer_getter:
            try:
                event_buffers = self.event_buffer_getter()
                if event_buffers:
                    for source_id, buffer in event_buffers.items():
                        if buffer:
                            size = buffer.size()
                            duration = buffer.get_duration()
                            diagnosis['event_buffer_status'][str(source_id)] = {
                                'size': size,
                                'duration': duration
                            }
                            
                            # Detect issues (buffer too large or empty when it shouldn't be)
                            if size > 1000:  # Arbitrary threshold
                                diagnosis['issues'].append({
                                    'type': 'event_buffer_overflow',
                                    'source_id': str(source_id),
                                    'size': size,
                                    'timestamp': datetime.now().isoformat()
                                })
            except Exception as e:
                self.logger.error(f"Error checking event buffer status: {e}", exc_info=True)
        
        return diagnosis
    
    def auto_fix_issue(self, issue: Dict) -> bool:
        """
        Automatically fix detected issue.
        
        Args:
            issue: Issue dictionary from diagnose_system_state()
            
        Returns:
            True if fix was applied, False otherwise
        """
        issue_type = issue.get('type')
        self.logger.info(f"Attempting to fix issue: {issue_type}")
        
        fix_applied = False
        fix_details = {
            'issue_type': issue_type,
            'timestamp': datetime.now().isoformat(),
            'method': None,
            'success': False
        }
        
        try:
            if issue_type == 'no_frames' or issue_type == 'capture_not_working':
                # Pipeline restart is now handled automatically in _grab_frames
                # But we can log and verify
                source = issue.get('source', 'Unknown')
                self.logger.info(f"Detected no frames for {source} - pipeline should auto-restart")
                fix_details['method'] = 'auto_restart_handled'
                fix_applied = True
                
            elif issue_type == 'memory_leak':
                # Trigger memory cleanup
                if self.memory_monitor:
                    self.memory_monitor.trigger_cleanup()
                    fix_details['method'] = 'memory_cleanup'
                    fix_applied = True
                else:
                    # Fallback: force GC
                    collected = gc.collect()
                    self.logger.info(f"Forced GC collected {collected} objects")
                    fix_details['method'] = 'force_gc'
                    fix_applied = True
                    
            elif issue_type == 'event_buffer_overflow':
                # Clear old frames from event buffer
                source_id = issue.get('source_id')
                if self.event_buffer_getter and source_id:
                    try:
                        event_buffers = self.event_buffer_getter()
                        if event_buffers and source_id in event_buffers:
                            buffer = event_buffers[source_id]
                            if buffer:
                                # Clear frames older than half the max duration
                                removed = buffer.clear_old_frames(older_than_seconds=buffer.max_duration_seconds / 2)
                                self.logger.info(f"Cleared {removed} old frames from EventBuffer for source {source_id}")
                                fix_details['method'] = 'event_buffer_cleanup'
                                fix_applied = True
                    except Exception as e:
                        self.logger.error(f"Error cleaning event buffer: {e}", exc_info=True)
                        
            elif issue_type == 'pre_event_frames':
                # This is usually a symptom, not a root cause
                # Log for monitoring but don't try to fix directly
                self.logger.debug(f"Pre-event frames issue detected (usually symptom of other problems)")
                fix_details['method'] = 'monitoring_only'
                fix_applied = False  # Not a direct fix
                
            else:
                self.logger.debug(f"No auto-fix available for issue type: {issue_type}")
                fix_details['method'] = 'no_fix_available'
                fix_applied = False
                
        except Exception as e:
            self.logger.error(f"Error applying fix for {issue_type}: {e}", exc_info=True)
            fix_details['error'] = str(e)
        
        fix_details['success'] = fix_applied
        self.fixes_applied.append(fix_details)
        
        if fix_applied:
            self.total_fixes_applied += 1
        
        return fix_applied
    
    def verify_fix(self, issue: Dict, wait_time: float = 10.0) -> bool:
        """
        Verify that fix resolved the issue.
        
        Args:
            issue: Original issue dictionary
            wait_time: Time to wait before verification
            
        Returns:
            True if issue is resolved, False otherwise
        """
        self.logger.debug(f"Verifying fix for {issue.get('type')}, waiting {wait_time}s...")
        time.sleep(wait_time)
        
        # Re-diagnose system
        new_diagnosis = self.diagnose_system_state()
        issue_type = issue.get('type')
        
        # Check if same type of issue still exists
        same_issue_found = any(
            i.get('type') == issue_type 
            for i in new_diagnosis.get('issues', [])
        )
        
        resolved = not same_issue_found
        
        verification = {
            'issue_type': issue_type,
            'timestamp': datetime.now().isoformat(),
            'resolved': resolved,
            'same_issue_found': same_issue_found
        }
        
        self.verification_results.append(verification)
        
        if resolved:
            self.logger.info(f"Issue {issue_type} appears to be resolved")
        else:
            self.logger.warning(f"Issue {issue_type} still present after fix")
        
        return resolved
    
    def _diagnostic_loop(self) -> None:
        """Main diagnostic loop."""
        self.logger.info("System diagnostics started")
        
        while self.running:
            try:
                self.last_check_time = time.time()
                self.total_checks += 1
                
                # Diagnose system state
                diagnosis = self.diagnose_system_state()
                
                # Log summary periodically
                if self.total_checks % 10 == 0:  # Every 10 checks
                    issue_count = len(diagnosis.get('issues', []))
                    self.logger.info(
                        f"Diagnostic check #{self.total_checks}: "
                        f"{issue_count} issues detected, "
                        f"{self.total_fixes_applied} fixes applied total"
                    )
                
                # Auto-fix issues if enabled
                if self.auto_fix:
                    for issue in diagnosis.get('issues', []):
                        # Only fix critical issues automatically
                        critical_types = ['no_frames', 'capture_not_working', 'memory_leak', 'event_buffer_overflow']
                        if issue.get('type') in critical_types:
                            fix_applied = self.auto_fix_issue(issue)
                            if fix_applied:
                                # Verify fix after a delay
                                self.verify_fix(issue, wait_time=15.0)
                
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"Error in diagnostic loop: {e}", exc_info=True)
                time.sleep(self.check_interval)
        
        self.logger.info("System diagnostics stopped")
    
    def start(self) -> None:
        """Start diagnostics in background thread."""
        if self.running:
            self.logger.warning("System diagnostics already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._diagnostic_loop, daemon=True, name="SystemDiagnostics")
        self.monitor_thread.start()
        self.logger.info("System diagnostics started")
    
    def stop(self) -> None:
        """Stop diagnostics."""
        if not self.running:
            return
        
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        
        # Print summary
        self.logger.info(
            f"System diagnostics stopped. Summary: "
            f"{self.total_checks} checks, "
            f"{self.total_issues_detected} issues detected, "
            f"{self.total_fixes_applied} fixes applied"
        )
    
    def get_summary(self) -> Dict:
        """Get summary of diagnostics.
        
        Returns:
            Dictionary with summary statistics
        """
        return {
            'running': self.running,
            'total_checks': self.total_checks,
            'total_issues_detected': self.total_issues_detected,
            'total_fixes_applied': self.total_fixes_applied,
            'issue_counts': dict(self.issue_counts),
            'last_check_time': self.last_check_time,
            'recent_issues': list(self.detected_issues)[-10:],
            'recent_fixes': list(self.fixes_applied)[-10:]
        }
