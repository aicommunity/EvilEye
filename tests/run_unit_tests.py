#!/usr/bin/env python3
"""
Скрипт для запуска unit тестов.
"""

import sys
import subprocess
from pathlib import Path
import argparse

def run_unit_tests(category=None, verbose=False, parallel=False):
    """Запускает unit тесты."""
    tests_dir = Path(__file__).parent
    unit_dir = tests_dir / 'unit'
    
    if not unit_dir.exists():
        print(f"Unit tests directory not found: {unit_dir}")
        return 1
    
    # Определяем путь для pytest
    if category:
        test_path = unit_dir / category
        if not test_path.exists():
            print(f"Category not found: {test_path}")
            return 1
    else:
        test_path = unit_dir
    
    # Собираем команду pytest
    cmd = ['python3', '-m', 'pytest']
    
    if verbose:
        cmd.append('-v')
    else:
        cmd.append('-q')
    
    if parallel:
        try:
            import pytest_xdist
            cmd.extend(['-n', 'auto'])
        except ImportError:
            print("pytest-xdist not installed, running sequentially")
    
    cmd.append(str(test_path))
    
    print(f"Running unit tests: {' '.join(cmd)}")
    print("=" * 80)
    
    result = subprocess.run(cmd, cwd=tests_dir.parent)
    return result.returncode

def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(description='Run unit tests')
    parser.add_argument('--category', 
                       help='Run tests for specific category (capture, detection, etc.)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-p', '--parallel', action='store_true',
                       help='Run tests in parallel (requires pytest-xdist)')
    
    args = parser.parse_args()
    
    exit_code = run_unit_tests(
        category=args.category,
        verbose=args.verbose,
        parallel=args.parallel
    )
    
    sys.exit(exit_code)

if __name__ == '__main__':
    main()

