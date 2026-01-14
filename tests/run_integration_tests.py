#!/usr/bin/env python3
"""
Скрипт для запуска integration тестов.
"""

import sys
import subprocess
from pathlib import Path
import argparse
import os

def check_environment():
    """Проверяет окружение для integration тестов."""
    warnings = []
    
    # Проверяем наличие тестовых данных
    if not Path('videos').exists() and not Path('EvilEyeData').exists():
        warnings.append("Test data directories (videos/, EvilEyeData/) not found")
    
    # Проверяем наличие конфигураций
    if not Path('evileye/samples_configs').exists():
        warnings.append("Sample configs directory not found")
    
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    return len(warnings) == 0

def run_integration_tests(category=None, verbose=False, markers=None):
    """Запускает integration тесты."""
    tests_dir = Path(__file__).parent
    integration_dir = tests_dir / 'integration'
    
    if not integration_dir.exists():
        print(f"Integration tests directory not found: {integration_dir}")
        return 1
    
    # Проверяем окружение
    check_environment()
    
    # Определяем путь для pytest
    if category:
        test_path = integration_dir / category
        if not test_path.exists():
            print(f"Category not found: {test_path}")
            return 1
    else:
        test_path = integration_dir
    
    # Собираем команду pytest
    cmd = ['python3', '-m', 'pytest']
    
    if verbose:
        cmd.append('-v')
    else:
        cmd.append('-q')
    
    # Добавляем маркеры если указаны
    if markers:
        cmd.extend(['-m', markers])
    
    cmd.append(str(test_path))
    
    print(f"Running integration tests: {' '.join(cmd)}")
    print("=" * 80)
    
    result = subprocess.run(cmd, cwd=tests_dir.parent)
    return result.returncode

def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(description='Run integration tests')
    parser.add_argument('--category', 
                       help='Run tests for specific category (capture, detection, etc.)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    parser.add_argument('-m', '--markers',
                       help='Run tests matching markers (e.g., "slow or database")')
    
    args = parser.parse_args()
    
    exit_code = run_integration_tests(
        category=args.category,
        verbose=args.verbose,
        markers=args.markers
    )
    
    sys.exit(exit_code)

if __name__ == '__main__':
    main()

