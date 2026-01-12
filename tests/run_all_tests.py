#!/usr/bin/env python3
"""
Скрипт для запуска всех тестов (unit и integration).
"""

import sys
import subprocess
from pathlib import Path
import argparse

def run_tests(test_type=None, category=None, verbose=False, coverage=False):
    """Запускает тесты."""
    tests_dir = Path(__file__).parent
    
    # Определяем пути для pytest
    if test_type == 'unit':
        test_paths = [str(tests_dir / 'unit')]
    elif test_type == 'integration':
        test_paths = [str(tests_dir / 'integration')]
    else:
        test_paths = [str(tests_dir / 'unit'), str(tests_dir / 'integration')]
    
    # Фильтруем по категории если указана
    if category:
        test_paths = [path for path in test_paths if category in path or Path(path).name == category]
    
    # Собираем команду pytest
    cmd = ['python3', '-m', 'pytest']
    
    if verbose:
        cmd.append('-v')
    else:
        cmd.append('-q')
    
    if coverage:
        cmd.extend(['--cov=evileye', '--cov-report=html', '--cov-report=term'])
    
    cmd.extend(test_paths)
    
    print(f"Running tests: {' '.join(cmd)}")
    print("=" * 80)
    
    result = subprocess.run(cmd, cwd=tests_dir.parent)
    return result.returncode

def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(description='Run all tests')
    parser.add_argument('--type', choices=['unit', 'integration'], 
                       help='Run only unit or integration tests')
    parser.add_argument('--category', 
                       help='Run tests for specific category (capture, detection, etc.)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('--coverage', action='store_true',
                       help='Generate coverage report')
    
    args = parser.parse_args()
    
    exit_code = run_tests(
        test_type=args.type,
        category=args.category,
        verbose=args.verbose,
        coverage=args.coverage
    )
    
    sys.exit(exit_code)

if __name__ == '__main__':
    main()

