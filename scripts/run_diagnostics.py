#!/usr/bin/env python3
"""
Script for running one-time system diagnostics on EvilEye.

Launches the system, performs diagnostics, applies automatic fixes, and generates a report.
"""

import argparse
import sys
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from evileye.controller.controller import Controller
from evileye.core.system_diagnostics import SystemDiagnostics
from evileye.core.memory_monitor import MemoryMonitor
from evileye.core.logging_config import setup_evileye_logging, get_logger
from evileye.core.logger import get_module_logger


class DiagnosticRunner:
    """Runner for one-time system diagnostics."""
    
    def __init__(self, 
                 config_path: str,
                 diagnostic_duration: int = 60,
                 check_interval: float = 10.0,
                 auto_fix: bool = True,
                 output_file: Optional[str] = None):
        """
        Initialize diagnostic runner.
        
        Args:
            config_path: Path to configuration file
            diagnostic_duration: Duration of diagnostics in seconds
            check_interval: Interval between diagnostic checks in seconds
            auto_fix: Whether to automatically apply fixes
            output_file: Optional path to save report
        """
        self.logger = get_module_logger("diagnostic_runner")
        self.config_path = config_path
        self.diagnostic_duration = diagnostic_duration
        self.check_interval = check_interval
        self.auto_fix = auto_fix
        self.output_file = output_file
        
        self.controller: Optional[Controller] = None
        self.diagnostics: Optional[SystemDiagnostics] = None
        self.memory_monitor: Optional[MemoryMonitor] = None
        
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.total_checks = 0
        self.all_issues: List[Dict] = []
        self.all_fixes: List[Dict] = []
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        self.shutdown_requested = False
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
    
    def _find_latest_log_file(self) -> Optional[str]:
        """Find the latest main log file (debug may be disabled by default)."""
        logs_dir = Path("logs")
        if not logs_dir.exists():
            return None
        
        log_files = sorted(
            logs_dir.glob("*_evileye_main.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        return str(log_files[0]) if log_files else None
    
    def _initialize_system(self) -> bool:
        """Initialize Controller and diagnostic components."""
        try:
            self.logger.info(f"Initializing system with config: {self.config_path}")
            
            # Setup logging
            setup_evileye_logging(log_level="INFO", log_to_console=True, log_to_file=True)
            
            # Create Controller
            self.controller = Controller()
            
            # Load configuration
            import json
            import os
            from evileye.utils.config_paths import normalize_config_path
            config_file_name = normalize_config_path(self.config_path)
            
            # Change working directory if needed (same logic as run_config_helper)
            config_dir = os.path.dirname(os.path.abspath(config_file_name))
            if config_dir:
                if os.path.basename(config_dir) == 'configs':
                    parent_dir = os.path.dirname(config_dir)
                    os.chdir(parent_dir)
                    self.logger.info(f"Changed working directory to parent of configs folder: {parent_dir}")
                else:
                    os.chdir(config_dir)
                    self.logger.info(f"Changed working directory to: {config_dir}")
            
            with open(config_file_name, 'r') as config_file:
                config_data = json.load(config_file)
            
            # Validate configuration
            from evileye.core.config_validator import ConfigValidator
            validator = ConfigValidator()
            is_valid, error_msg = validator.validate_full_config(config_data)
            if not is_valid:
                self.logger.warning(f"Configuration validation warning: {error_msg}")
                self.logger.info("Continuing with potentially invalid configuration...")
            else:
                self.logger.info("Configuration validated successfully")
            
            # Ensure controller section exists
            config_data.setdefault("controller", {})
            
            # Initialize Controller
            self.controller.init(config_data)
            
            # Find log file
            log_file = self._find_latest_log_file()
            if log_file:
                self.logger.info(f"Using log file: {log_file}")
            
            # Create MemoryMonitor (without background thread)
            self.memory_monitor = MemoryMonitor(
                check_interval=self.check_interval,
                leak_threshold_mb=50.0,
                leak_window_samples=20,
                auto_cleanup=False  # Manual control
            )
            
            # Create SystemDiagnostics (without background thread)
            self.diagnostics = SystemDiagnostics(
                log_file=log_file,
                check_interval=self.check_interval,
                auto_fix=self.auto_fix
            )
            
            # Setup callbacks for diagnostics
            self.diagnostics.set_pipeline_getter(lambda: self.controller.pipeline if self.controller else None)
            self.diagnostics.set_event_buffer_getter(lambda: self.controller.event_buffers if self.controller else {})
            self.diagnostics.set_memory_monitor(self.memory_monitor)
            
            self.logger.info("System initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize system: {e}", exc_info=True)
            return False
    
    def _start_system(self) -> bool:
        """Start the system."""
        try:
            self.logger.info("Starting system...")
            if not self.controller:
                self.logger.error("Controller not initialized")
                return False
            
            self.controller.start()
            
            # Wait for initialization
            self.logger.info("Waiting for system initialization (10 seconds)...")
            time.sleep(10)
            
            self.logger.info("System started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start system: {e}", exc_info=True)
            return False
    
    def _run_diagnostic_cycle(self) -> Dict:
        """Run a single diagnostic cycle."""
        cycle_result = {
            'timestamp': datetime.now().isoformat(),
            'issues': [],
            'fixes': [],
            'memory_stats': None,
            'capture_status': {},
            'event_buffer_status': {}
        }
        
        try:
            # Perform system diagnosis
            if self.diagnostics:
                diagnosis = self.diagnostics.diagnose_system_state()
                cycle_result['issues'] = diagnosis.get('issues', [])
                cycle_result['capture_status'] = diagnosis.get('capture_status', {})
                cycle_result['event_buffer_status'] = diagnosis.get('event_buffer_status', {})
                
                # Store issues
                self.all_issues.extend(cycle_result['issues'])
                
                # Apply fixes for critical issues
                if self.auto_fix:
                    critical_types = ['no_frames', 'capture_not_working', 'memory_leak', 'event_buffer_overflow']
                    for issue in cycle_result['issues']:
                        if issue.get('type') in critical_types:
                            fix_applied = self.diagnostics.auto_fix_issue(issue)
                            if fix_applied:
                                cycle_result['fixes'].append({
                                    'issue_type': issue.get('type'),
                                    'source': issue.get('source', 'Unknown'),
                                    'timestamp': datetime.now().isoformat()
                                })
                                self.all_fixes.append(cycle_result['fixes'][-1])
                                
                                # Wait a bit and verify fix
                                time.sleep(5)
                                self.diagnostics.verify_fix(issue, wait_time=5.0)
            
            # Get memory statistics
            if self.memory_monitor:
                memory_stats = self.memory_monitor.get_memory_stats()
                if memory_stats:
                    cycle_result['memory_stats'] = memory_stats
            
            self.total_checks += 1
            
        except Exception as e:
            self.logger.error(f"Error in diagnostic cycle: {e}", exc_info=True)
        
        return cycle_result
    
    def _generate_report(self) -> str:
        """Generate diagnostic report."""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("EvilEye System Diagnostics Report")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")
        
        # Configuration info
        report_lines.append(f"Configuration: {self.config_path}")
        if self.start_time and self.end_time:
            actual_duration = self.end_time - self.start_time
            report_lines.append(f"Duration: {actual_duration:.1f}s (requested: {self.diagnostic_duration}s)")
        else:
            report_lines.append(f"Duration: {self.diagnostic_duration}s")
        report_lines.append(f"Checks performed: {self.total_checks}")
        report_lines.append(f"Auto-fix enabled: {self.auto_fix}")
        report_lines.append("")
        
        # Memory statistics
        report_lines.append("--- Memory Statistics ---")
        if self.memory_monitor:
            memory_summary = self.memory_monitor.get_summary()
            if memory_summary.get('current_stats'):
                stats = memory_summary['current_stats']
                report_lines.append(f"Initial RSS: {memory_summary.get('initial_rss_mb', 0):.1f} MB")
                report_lines.append(f"Current RSS: {stats.get('rss_mb', 0):.1f} MB")
                report_lines.append(f"Peak RSS: {memory_summary.get('peak_rss_mb', 0):.1f} MB")
                report_lines.append(f"Growth: {stats.get('growth_mb', 0):+.1f} MB")
                report_lines.append(f"Leaks detected: {memory_summary.get('leak_detected_count', 0)}")
                report_lines.append(f"Cleanups triggered: {memory_summary.get('cleanup_triggered_count', 0)}")
            else:
                report_lines.append("Memory statistics not available")
        else:
            report_lines.append("Memory monitor not initialized")
        report_lines.append("")
        
        # Issues detected
        report_lines.append("--- Issues Detected ---")
        if self.diagnostics:
            diag_summary = self.diagnostics.get_summary()
            total_issues = diag_summary.get('total_issues_detected', len(self.all_issues))
            report_lines.append(f"Total issues: {total_issues}")
            
            issue_counts = diag_summary.get('issue_counts', {})
            if issue_counts:
                report_lines.append("By type:")
                for issue_type, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
                    report_lines.append(f"  - {issue_type}: {count}")
            
            recent_issues = diag_summary.get('recent_issues', [])
            if recent_issues:
                report_lines.append("Recent issues:")
                for issue in recent_issues[-10:]:  # Last 10
                    issue_type = issue.get('type', 'unknown')
                    source = issue.get('source', 'Unknown')
                    timestamp = issue.get('timestamp', '')
                    report_lines.append(f"  - [{timestamp}] {issue_type} for {source}")
        else:
            report_lines.append("Diagnostics not initialized")
        report_lines.append("")
        
        # Fixes applied
        report_lines.append("--- Fixes Applied ---")
        if self.diagnostics:
            diag_summary = self.diagnostics.get_summary()
            total_fixes = diag_summary.get('total_fixes_applied', len(self.all_fixes))
            report_lines.append(f"Total fixes: {total_fixes}")
            
            recent_fixes = diag_summary.get('recent_fixes', [])
            if recent_fixes:
                report_lines.append("Recent fixes:")
                for fix in recent_fixes[-10:]:  # Last 10
                    issue_type = fix.get('issue_type', 'unknown')
                    method = fix.get('method', 'unknown')
                    success = fix.get('success', False)
                    timestamp = fix.get('timestamp', '')
                    status = "SUCCESS" if success else "FAILED"
                    report_lines.append(f"  - [{timestamp}] {issue_type} via {method} ({status})")
        else:
            report_lines.append("No fixes applied")
        report_lines.append("")
        
        # Capture status (from last diagnostic cycle)
        report_lines.append("--- Capture Status ---")
        if self.diagnostics:
            # Get latest diagnosis
            try:
                diagnosis = self.diagnostics.diagnose_system_state()
                capture_status = diagnosis.get('capture_status', {})
                if capture_status:
                    for source_name, status in capture_status.items():
                        is_working = status.get('is_working', False)
                        is_inited = status.get('is_inited', False)
                        source_type = status.get('source_type', 'unknown')
                        report_lines.append(f"{source_name}: working={is_working}, inited={is_inited}, type={source_type}")
                else:
                    report_lines.append("No capture sources found")
            except Exception as e:
                report_lines.append(f"Error getting capture status: {e}")
        else:
            report_lines.append("Diagnostics not initialized")
        report_lines.append("")
        
        # Event buffer status
        report_lines.append("--- Event Buffer Status ---")
        if self.diagnostics:
            try:
                diagnosis = self.diagnostics.diagnose_system_state()
                buffer_status = diagnosis.get('event_buffer_status', {})
                if buffer_status:
                    for source_id, status in buffer_status.items():
                        size = status.get('size', 0)
                        duration = status.get('duration', 0.0)
                        report_lines.append(f"Source {source_id}: size={size}, duration={duration:.1f}s")
                else:
                    report_lines.append("No event buffers found")
            except Exception as e:
                report_lines.append(f"Error getting buffer status: {e}")
        else:
            report_lines.append("Event buffers not initialized")
        report_lines.append("")
        
        # Recommendations
        report_lines.append("--- Recommendations ---")
        recommendations = []
        
        if self.memory_monitor:
            memory_summary = self.memory_monitor.get_summary()
            if memory_summary.get('leak_detected_count', 0) > 0:
                recommendations.append("Memory leaks detected - consider investigating EventBuffer and EventRecorder cleanup")
        
        if self.diagnostics:
            diag_summary = self.diagnostics.get_summary()
            issue_counts = diag_summary.get('issue_counts', {})
            if issue_counts.get('no_frames', 0) > 0:
                recommendations.append("No frames issues detected - check video sources and pipeline configuration")
            if issue_counts.get('capture_not_working', 0) > 0:
                recommendations.append("Capture not working issues - verify source connectivity and pipeline state")
            if issue_counts.get('event_buffer_overflow', 0) > 0:
                recommendations.append("Event buffer overflow - consider reducing buffer duration or increasing cleanup frequency")
        
        if not recommendations:
            recommendations.append("No critical issues detected - system appears to be functioning normally")
        
        for rec in recommendations:
            report_lines.append(f"  - {rec}")
        
        report_lines.append("")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def _save_report(self, report: str) -> None:
        """Save report to file."""
        if not self.output_file:
            return
        
        try:
            output_path = Path(self.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            self.logger.info(f"Report saved to: {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to save report: {e}", exc_info=True)
    
    def run(self) -> int:
        """
        Run diagnostic process.
        
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        try:
            # Initialize system
            if not self._initialize_system():
                self.logger.error("Failed to initialize system")
                return 1
            
            # Start system
            if not self._start_system():
                self.logger.error("Failed to start system")
                return 1
            
            # Run diagnostic cycles
            self.start_time = time.time()
            self.logger.info(f"Starting diagnostic cycles (duration: {self.diagnostic_duration}s, interval: {self.check_interval}s)")
            
            cycles = 0
            while (time.time() - self.start_time) < self.diagnostic_duration:
                if self.shutdown_requested:
                    self.logger.info("Shutdown requested, stopping diagnostics...")
                    break
                
                cycles += 1
                elapsed = time.time() - self.start_time
                self.logger.info(f"Diagnostic cycle {cycles} (elapsed: {elapsed:.1f}s)")
                
                cycle_result = self._run_diagnostic_cycle()
                
                # Log cycle results
                issues_count = len(cycle_result.get('issues', []))
                fixes_count = len(cycle_result.get('fixes', []))
                if issues_count > 0 or fixes_count > 0:
                    self.logger.info(f"Cycle {cycles}: {issues_count} issues, {fixes_count} fixes applied")
                
                # Wait before next cycle (unless shutdown requested or time expired)
                remaining_time = self.diagnostic_duration - (time.time() - self.start_time)
                if remaining_time > 0 and not self.shutdown_requested:
                    sleep_time = min(self.check_interval, remaining_time)
                    time.sleep(sleep_time)
            
            self.end_time = time.time()
            
            # Generate and save report
            self.logger.info("Generating diagnostic report...")
            report = self._generate_report()
            print("\n" + report)
            self._save_report(report)
            
            # Stop system before returning
            self._stop_system()
            
            return 0
            
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
            self.shutdown_requested = True
            self._stop_system()
            return 130
        except Exception as e:
            self.logger.error(f"Error during diagnostics: {e}", exc_info=True)
            self._stop_system()
            return 1
    
    def _stop_system(self) -> None:
        """Stop the system."""
        try:
            if self.controller:
                self.logger.info("Stopping system...")
                
                # Set run_flag to False to stop main loop
                if hasattr(self.controller, 'run_flag'):
                    self.controller.run_flag = False
                    self.logger.debug("Set controller.run_flag = False")
                
                # Stop controller (this will stop pipeline and all components)
                try:
                    self.controller.stop()
                    self.logger.debug("Controller.stop() called")
                except Exception as e:
                    self.logger.warning(f"Error in controller.stop(): {e}", exc_info=True)
                
                # Wait for control thread to finish
                if hasattr(self.controller, 'control_thread') and self.controller.control_thread.is_alive():
                    self.logger.debug("Waiting for control thread to finish...")
                    self.controller.control_thread.join(timeout=5.0)
                    if self.controller.control_thread.is_alive():
                        self.logger.warning("Control thread did not finish within timeout")
                
                # Wait a bit for other threads to finish
                time.sleep(1)
                
                # Release resources
                try:
                    self.controller.release()
                    self.logger.debug("Controller.release() called")
                except Exception as e:
                    self.logger.warning(f"Error in controller.release(): {e}", exc_info=True)
                
                # Clear controller reference
                self.controller = None
                
                self.logger.info("System stopped successfully")
        except Exception as e:
            self.logger.error(f"Error stopping system: {e}", exc_info=True)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run one-time system diagnostics on EvilEye",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run diagnostics for 60 seconds with default settings
  python scripts/run_diagnostics.py --config configs/poly-videos-gst.json
  
  # Run diagnostics for 120 seconds, check every 15 seconds
  python scripts/run_diagnostics.py --config configs/poly-videos-gst.json --duration 120 --interval 15
  
  # Run diagnostics without auto-fix
  python scripts/run_diagnostics.py --config configs/poly-videos-gst.json --no-fix
  
  # Save report to file
  python scripts/run_diagnostics.py --config configs/poly-videos-gst.json --output reports/diagnostic_report.txt
        """
    )
    
    parser.add_argument(
        '--config',
        required=True,
        type=str,
        help='Path to configuration file'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=60,
        help='Duration of diagnostics in seconds (default: 60)'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=10.0,
        help='Interval between diagnostic checks in seconds (default: 10.0)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Path to save diagnostic report file'
    )
    parser.add_argument(
        '--no-fix',
        action='store_true',
        help='Disable automatic fixing (diagnostics only)'
    )
    
    args = parser.parse_args()
    
    # Validate config file
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file not found: {args.config}")
        return 1
    
    # Create runner
    runner = DiagnosticRunner(
        config_path=str(config_path),
        diagnostic_duration=args.duration,
        check_interval=args.interval,
        auto_fix=not args.no_fix,
        output_file=args.output
    )
    
    # Run diagnostics
    exit_code = runner.run()
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
