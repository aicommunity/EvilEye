#!/usr/bin/env python3
"""
Wrapper for evileye CLI that ensures proper path setup and auto-fixes entry points
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if project_root.exists():
    sys.path.insert(0, str(project_root))

# Also add current directory to path for direct execution
current_dir = Path(__file__).parent
if current_dir.exists():
    sys.path.insert(0, str(current_dir))

# No auto-fix needed - entry points are now self-healing

from evileye.cli import main

if __name__ == '__main__':
    sys.exit(main())
