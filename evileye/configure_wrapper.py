#!/usr/bin/env python3
"""
Wrapper for evileye configure that ensures proper path setup
"""
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
if project_root.exists():
    sys.path.insert(0, str(project_root))

from evileye.configure import start_configurer

if __name__ == '__main__':
    sys.exit(start_configurer())
