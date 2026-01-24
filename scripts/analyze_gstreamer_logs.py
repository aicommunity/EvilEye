#!/usr/bin/env python3
"""
Analyze GStreamer logs for patterns and issues.

Parses log files, identifies error patterns, creates timeline,
and generates recommendations.
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict, Counter


class LogAnalyzer:
    """Analyze GStreamer logs for issues and patterns."""
    
    # Error patterns
    ERROR_PATTERNS = {
        'no_frames': re.compile(r'Pipeline PLAYING but no frames received after (\d+)s'),
        'none_image': re.compile(r'Received None image|All images are None'),
        'processing_error': re.compile(r'Error processing frame|Failed to extract frame data'),
        'loop_restart_failed': re.compile(r'Loop restart failed'),
        'attribute_error': re.compile(r'AttributeError.*clear|AttributeError.*Queue'),
        'pre_event_frames': re.compile(r'No pre-event frames found'),
        'pipeline_restart': re.compile(r'Looping video: pipeline restarted successfully'),
        'first_frame': re.compile(r'First frame received ([\d.]+)s after init'),
        'eos_received': re.compile(r'GStreamer EOS received'),
        'pipeline_error': re.compile(r'GStreamer pipeline ERROR|Failed to.*pipeline'),
    }
    
    # Info patterns
    INFO_PATTERNS = {
        'pipeline_init': re.compile(r'GStreamer pipeline initialized successfully'),
        'pipeline_playing': re.compile(r'pipeline restarted successfully.*state=.*PLAYING'),
        'reconnect': re.compile(r'Reconnected to.*source'),
    }
    
    def __init__(self, log_file: str):
        """
        Initialize log analyzer.
        
        Args:
            log_file: Path to log file
        """
        self.log_file = log_file
        self.lines: List[Dict] = []
        self.issues: List[Dict] = []
        self.events: List[Dict] = []
        
    def parse_log(self):
        """Parse log file and extract events."""
        print(f"Parsing log file: {self.log_file}")
        
        if not os.path.exists(self.log_file):
            print(f"ERROR: Log file not found: {self.log_file}")
            return
        
        with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Parse timestamp and log level
                timestamp = None
                level = None
                message = line
                
                # Try to parse standard log format: YYYY-MM-DD HH:MM:SS,mmm - LEVEL - message
                timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})', line)
                if timestamp_match:
                    timestamp_str = timestamp_match.group(1)
                    try:
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                    except ValueError:
                        pass
                
                # Extract log level
                level_match = re.search(r' - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ', line)
                if level_match:
                    level = level_match.group(1)
                    # Extract message after level
                    parts = line.split(f' - {level} - ', 1)
                    if len(parts) > 1:
                        message = parts[1]
                
                log_entry = {
                    'line_num': line_num,
                    'timestamp': timestamp,
                    'level': level or 'UNKNOWN',
                    'message': message,
                    'raw': line
                }
                
                self.lines.append(log_entry)
                
                # Check for error patterns
                for error_type, pattern in self.ERROR_PATTERNS.items():
                    match = pattern.search(message)
                    if match:
                        issue = {
                            'type': error_type,
                            'line_num': line_num,
                            'timestamp': timestamp,
                            'level': level or 'WARNING',
                            'message': message,
                            'match': match.group(0),
                            'groups': match.groups()
                        }
                        self.issues.append(issue)
                
                # Check for info patterns
                for event_type, pattern in self.INFO_PATTERNS.items():
                    match = pattern.search(message)
                    if match:
                        event = {
                            'type': event_type,
                            'line_num': line_num,
                            'timestamp': timestamp,
                            'level': level or 'INFO',
                            'message': message,
                            'match': match.group(0)
                        }
                        self.events.append(event)
        
        print(f"Parsed {len(self.lines)} lines")
        print(f"Found {len(self.issues)} issues")
        print(f"Found {len(self.events)} events")
    
    def analyze_issues(self) -> Dict:
        """Analyze detected issues."""
        analysis = {
            'total_issues': len(self.issues),
            'issues_by_type': Counter(),
            'issues_by_level': Counter(),
            'timeline': [],
            'correlations': {}
        }
        
        # Count issues by type
        for issue in self.issues:
            analysis['issues_by_type'][issue['type']] += 1
            analysis['issues_by_level'][issue.get('level', 'UNKNOWN')] += 1
        
        # Create timeline
        timeline_entries = []
        for issue in self.issues:
            if issue.get('timestamp'):
                timeline_entries.append({
                    'time': issue['timestamp'],
                    'type': issue['type'],
                    'message': issue['message'][:100]
                })
        
        timeline_entries.sort(key=lambda x: x['time'] if x['time'] else datetime.min)
        analysis['timeline'] = timeline_entries
        
        # Find correlations
        # Group issues by time windows
        if timeline_entries:
            time_windows = defaultdict(list)
            for entry in timeline_entries:
                if entry['time']:
                    # Round to nearest minute
                    window_key = entry['time'].replace(second=0, microsecond=0)
                    time_windows[window_key].append(entry['type'])
            
            # Find common co-occurrences
            co_occurrences = defaultdict(int)
            for window, types in time_windows.items():
                if len(types) > 1:
                    # All pairs in this window
                    for i, t1 in enumerate(types):
                        for t2 in types[i+1:]:
                            pair = tuple(sorted([t1, t2]))
                            co_occurrences[pair] += 1
            
            analysis['correlations'] = dict(sorted(
                co_occurrences.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])  # Top 10 correlations
        
        return analysis
    
    def analyze_events(self) -> Dict:
        """Analyze system events."""
        analysis = {
            'total_events': len(self.events),
            'events_by_type': Counter(),
            'event_timeline': []
        }
        
        for event in self.events:
            analysis['events_by_type'][event['type']] += 1
        
        # Create event timeline
        event_timeline = []
        for event in self.events:
            if event.get('timestamp'):
                event_timeline.append({
                    'time': event['timestamp'],
                    'type': event['type'],
                    'message': event['message'][:100]
                })
        
        event_timeline.sort(key=lambda x: x['time'] if x['time'] else datetime.min)
        analysis['event_timeline'] = event_timeline
        
        return analysis
    
    def find_patterns(self) -> Dict:
        """Find patterns in issues and events."""
        patterns = {
            'restart_cycles': [],
            'error_sequences': [],
            'recovery_patterns': []
        }
        
        # Find restart cycles (EOS -> restart -> first frame)
        restart_cycles = []
        eos_events = [e for e in self.events if e['type'] == 'eos_received']
        restart_events = [e for e in self.events if e['type'] == 'pipeline_restart']
        first_frame_events = [e for e in self.events if e['type'] == 'first_frame']
        
        for eos in eos_events:
            if not eos.get('timestamp'):
                continue
            
            # Find next restart after EOS
            next_restart = None
            for restart in restart_events:
                if restart.get('timestamp') and restart['timestamp'] > eos['timestamp']:
                    next_restart = restart
                    break
            
            if next_restart:
                # Find first frame after restart
                next_frame = None
                for frame in first_frame_events:
                    if frame.get('timestamp') and frame['timestamp'] > next_restart['timestamp']:
                        next_frame = frame
                        break
                
                cycle = {
                    'eos_time': eos['timestamp'],
                    'restart_time': next_restart['timestamp'],
                    'first_frame_time': next_frame['timestamp'] if next_frame else None,
                    'restart_duration': None,
                    'frame_delay': None
                }
                
                if next_frame:
                    cycle['restart_duration'] = (next_restart['timestamp'] - eos['timestamp']).total_seconds()
                    cycle['frame_delay'] = (next_frame['timestamp'] - next_restart['timestamp']).total_seconds()
                
                restart_cycles.append(cycle)
        
        patterns['restart_cycles'] = restart_cycles
        
        # Find error sequences (multiple errors in short time)
        error_sequences = []
        if self.issues:
            current_sequence = [self.issues[0]]
            for issue in self.issues[1:]:
                if issue.get('timestamp') and current_sequence[-1].get('timestamp'):
                    time_diff = (issue['timestamp'] - current_sequence[-1]['timestamp']).total_seconds()
                    if time_diff < 5.0:  # Within 5 seconds
                        current_sequence.append(issue)
                    else:
                        if len(current_sequence) > 1:
                            error_sequences.append(current_sequence)
                        current_sequence = [issue]
                else:
                    current_sequence.append(issue)
            
            if len(current_sequence) > 1:
                error_sequences.append(current_sequence)
        
        patterns['error_sequences'] = [
            {
                'count': len(seq),
                'types': [i['type'] for i in seq],
                'duration': (seq[-1]['timestamp'] - seq[0]['timestamp']).total_seconds()
                if seq[-1].get('timestamp') and seq[0].get('timestamp') else None
            }
            for seq in error_sequences
        ]
        
        return patterns
    
    def generate_recommendations(self, issue_analysis: Dict, 
                                event_analysis: Dict, 
                                patterns: Dict) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        # Check issue frequency
        total_issues = issue_analysis.get('total_issues', 0)
        if total_issues > 50:
            recommendations.append(
                f"High number of issues detected ({total_issues}). "
                "Review system configuration and pipeline setup."
            )
        
        # Check specific issue types
        issues_by_type = issue_analysis.get('issues_by_type', {})
        if issues_by_type.get('no_frames', 0) > 5:
            recommendations.append(
                "Multiple 'no frames received' errors detected. "
                "Check pipeline restart logic and appsink callback connection."
            )
        
        if issues_by_type.get('none_image', 0) > 5:
            recommendations.append(
                "Multiple 'None image' errors detected. "
                "Review last_frame cleanup logic and memory management."
            )
        
        if issues_by_type.get('loop_restart_failed', 0) > 0:
            recommendations.append(
                "Pipeline restart failures detected. "
                "Review _init_pipeline() error handling and pipeline state management."
            )
        
        # Check restart cycles
        restart_cycles = patterns.get('restart_cycles', [])
        if restart_cycles:
            avg_frame_delay = sum(
                c['frame_delay'] for c in restart_cycles 
                if c.get('frame_delay') is not None
            ) / len([c for c in restart_cycles if c.get('frame_delay') is not None])
            
            if avg_frame_delay > 15.0:
                recommendations.append(
                    f"Average frame delay after restart is {avg_frame_delay:.1f}s (threshold: 15s). "
                    "This may indicate issues with pipeline initialization or callback setup."
                )
        
        # Check error sequences
        error_sequences = patterns.get('error_sequences', [])
        if error_sequences:
            long_sequences = [s for s in error_sequences if s.get('count', 0) > 3]
            if long_sequences:
                recommendations.append(
                    f"Found {len(long_sequences)} error sequences with >3 errors. "
                    "These may indicate cascading failures. Review error handling."
                )
        
        # Check correlations
        correlations = issue_analysis.get('correlations', {})
        if correlations:
            top_correlation = max(correlations.items(), key=lambda x: x[1])
            recommendations.append(
                f"Strong correlation detected between {top_correlation[0][0]} and {top_correlation[0][1]} "
                f"(co-occurred {top_correlation[1]} times). "
                "These issues may be related."
            )
        
        if not recommendations:
            recommendations.append("No specific issues detected. System appears to be functioning normally.")
        
        return recommendations
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """
        Generate analysis report.
        
        Args:
            output_file: Optional file to save report
            
        Returns:
            Report as string
        """
        # Parse log
        self.parse_log()
        
        # Analyze
        issue_analysis = self.analyze_issues()
        event_analysis = self.analyze_events()
        patterns = self.find_patterns()
        recommendations = self.generate_recommendations(
            issue_analysis, event_analysis, patterns
        )
        
        # Generate report
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("GStreamer Log Analysis Report")
        report_lines.append("=" * 80)
        report_lines.append(f"Log file: {self.log_file}")
        report_lines.append(f"Generated: {datetime.now().isoformat()}")
        report_lines.append("")
        
        # Summary
        report_lines.append("SUMMARY")
        report_lines.append("-" * 80)
        report_lines.append(f"Total log lines: {len(self.lines)}")
        report_lines.append(f"Total issues: {issue_analysis['total_issues']}")
        report_lines.append(f"Total events: {event_analysis['total_events']}")
        report_lines.append("")
        
        # Issues by type
        if issue_analysis['issues_by_type']:
            report_lines.append("ISSUES BY TYPE")
            report_lines.append("-" * 80)
            for issue_type, count in issue_analysis['issues_by_type'].most_common():
                report_lines.append(f"  {issue_type}: {count}")
            report_lines.append("")
        
        # Issues by level
        if issue_analysis['issues_by_level']:
            report_lines.append("ISSUES BY LEVEL")
            report_lines.append("-" * 80)
            for level, count in issue_analysis['issues_by_level'].most_common():
                report_lines.append(f"  {level}: {count}")
            report_lines.append("")
        
        # Restart cycles
        restart_cycles = patterns.get('restart_cycles', [])
        if restart_cycles:
            report_lines.append("RESTART CYCLES")
            report_lines.append("-" * 80)
            report_lines.append(f"  Total cycles: {len(restart_cycles)}")
            if restart_cycles:
                avg_restart = sum(
                    c['restart_duration'] for c in restart_cycles 
                    if c.get('restart_duration') is not None
                ) / len([c for c in restart_cycles if c.get('restart_duration') is not None])
                avg_delay = sum(
                    c['frame_delay'] for c in restart_cycles 
                    if c.get('frame_delay') is not None
                ) / len([c for c in restart_cycles if c.get('frame_delay') is not None])
                report_lines.append(f"  Average restart duration: {avg_restart:.2f}s")
                report_lines.append(f"  Average frame delay: {avg_delay:.2f}s")
            report_lines.append("")
        
        # Correlations
        correlations = issue_analysis.get('correlations', {})
        if correlations:
            report_lines.append("ISSUE CORRELATIONS")
            report_lines.append("-" * 80)
            for (type1, type2), count in list(correlations.items())[:5]:
                report_lines.append(f"  {type1} <-> {type2}: {count} co-occurrences")
            report_lines.append("")
        
        # Recommendations
        report_lines.append("RECOMMENDATIONS")
        report_lines.append("-" * 80)
        for i, rec in enumerate(recommendations, 1):
            report_lines.append(f"  {i}. {rec}")
        report_lines.append("")
        
        report_lines.append("=" * 80)
        
        report = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            print(f"Report saved to: {output_file}")
        
        return report


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Analyze GStreamer logs for patterns and issues"
    )
    parser.add_argument(
        'log_file',
        help='Path to log file'
    )
    parser.add_argument(
        '--output',
        help='Output file for report'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )
    
    args = parser.parse_args()
    
    analyzer = LogAnalyzer(args.log_file)
    report = analyzer.generate_report(output_file=args.output)
    
    if not args.json:
        print(report)
    else:
        # Output as JSON
        data = {
            'log_file': args.log_file,
            'total_lines': len(analyzer.lines),
            'total_issues': len(analyzer.issues),
            'total_events': len(analyzer.events),
            'issues_by_type': dict(analyzer.analyze_issues()['issues_by_type']),
            'recommendations': analyzer.generate_recommendations(
                analyzer.analyze_issues(),
                analyzer.analyze_events(),
                analyzer.find_patterns()
            )
        }
        print(json.dumps(data, indent=2, default=str))


if __name__ == '__main__':
    main()
