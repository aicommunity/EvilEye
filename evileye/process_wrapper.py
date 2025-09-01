#!/usr/bin/env python3
"""
Wrapper for evileye process that ensures proper path setup and auto-fixes entry points
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if project_root.exists():
    sys.path.insert(0, str(project_root))

# No auto-fix needed - entry points are now self-healing

from evileye.process import main

if __name__ == '__main__':
    sys.exit(main())
