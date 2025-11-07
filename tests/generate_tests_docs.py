#!/usr/bin/env python3
"""
Скрипт для автоматической генерации документации тестов.
Сканирует все тесты и создает markdown документацию.
"""

import os
import ast
import re
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

def extract_test_info(file_path: Path) -> Dict:
    """Извлекает информацию о тесте из файла."""
    info = {
        'file': str(file_path),
        'name': file_path.name,
        'path': file_path.relative_to(Path(__file__).parent),
        'type': None,  # unit или integration
        'category': None,
        'subcategory': None,
        'module': None,
        'description': '',
        'test_functions': [],
        'test_classes': [],
        'imports': [],
    }
    
    # Определяем тип и категорию из пути
    path_parts = info['path'].parts
    if 'unit' in path_parts:
        info['type'] = 'unit'
    elif 'integration' in path_parts:
        info['type'] = 'integration'
    
    if len(path_parts) >= 3:
        info['category'] = path_parts[1]  # unit/integration
        if len(path_parts) >= 4:
            info['category'] = path_parts[2]  # category
            if len(path_parts) >= 5:
                info['subcategory'] = path_parts[3]  # subcategory
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Парсим AST
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return info
        
        # Извлекаем docstring модуля
        if ast.get_docstring(tree):
            info['description'] = ast.get_docstring(tree)
        
        # Извлекаем импорты
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    info['imports'].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    info['imports'].append(node.module)
        
        # Извлекаем тестовые функции и классы
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith('test_'):
                    func_info = {
                        'name': node.name,
                        'description': ast.get_docstring(node) or '',
                    }
                    info['test_functions'].append(func_info)
            
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith('Test'):
                    class_info = {
                        'name': node.name,
                        'description': ast.get_docstring(node) or '',
                        'methods': [],
                    }
                    # Извлекаем методы класса
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if item.name.startswith('test_'):
                                method_info = {
                                    'name': item.name,
                                    'description': ast.get_docstring(item) or '',
                                }
                                class_info['methods'].append(method_info)
                    info['test_classes'].append(class_info)
        
        # Определяем модуль из импортов
        for imp in info['imports']:
            if imp.startswith('evileye.'):
                parts = imp.split('.')
                if len(parts) >= 2:
                    info['module'] = parts[1]
                    break
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    
    return info

def generate_documentation():
    """Генерирует документацию тестов."""
    tests_dir = Path(__file__).parent
    all_tests = []
    
    # Собираем все тесты
    for test_file in tests_dir.rglob('test_*.py'):
        if test_file.name in ['generate_tests_docs.py', 'analyze_tests.py', 'migrate_tests.py']:
            continue
        info = extract_test_info(test_file)
        all_tests.append(info)
    
    # Группируем по типам и категориям
    by_type = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for test in all_tests:
        test_type = test['type'] or 'unknown'
        category = test['category'] or 'unknown'
        subcategory = test['subcategory'] or 'general'
        
        by_type[test_type][category][subcategory].append(test)
    
    # Генерируем полную документацию
    doc_file = tests_dir / 'TESTS_DOCUMENTATION.md'
    with open(doc_file, 'w', encoding='utf-8') as f:
        f.write("# Документация тестов EvilEye\n\n")
        f.write("Автоматически сгенерированная документация всех тестов.\n\n")
        f.write(f"Всего тестов: {len(all_tests)}\n\n")
        f.write("## Содержание\n\n")
        
        # Содержание
        for test_type in sorted(by_type.keys()):
            f.write(f"### {test_type.upper()} тесты\n\n")
            for category in sorted(by_type[test_type].keys()):
                f.write(f"- [{category}](#{test_type}-{category})\n")
            f.write("\n")
        
        # Документация по типам
        for test_type in sorted(by_type.keys()):
            f.write(f"\n## {test_type.upper()} тесты\n\n")
            
            for category in sorted(by_type[test_type].keys()):
                f.write(f"### {category}\n\n")
                
                for subcategory in sorted(by_type[test_type][category].keys()):
                    if subcategory != 'general':
                        f.write(f"#### {subcategory}\n\n")
                    
                    tests = by_type[test_type][category][subcategory]
                    for test in sorted(tests, key=lambda x: x['name']):
                        f.write(f"##### {test['name']}\n\n")
                        
                        if test['description']:
                            f.write(f"{test['description']}\n\n")
                        
                        f.write(f"- **Путь**: `{test['path']}`\n")
                        if test['module']:
                            f.write(f"- **Модуль**: `evileye.{test['module']}`\n")
                        
                        if test['test_classes']:
                            f.write(f"- **Тестовые классы**:\n")
                            for cls in test['test_classes']:
                                f.write(f"  - `{cls['name']}`")
                                if cls['description']:
                                    f.write(f": {cls['description']}")
                                f.write("\n")
                                if cls['methods']:
                                    for method in cls['methods']:
                                        f.write(f"    - `{method['name']}`")
                                        if method['description']:
                                            f.write(f": {method['description']}")
                                        f.write("\n")
                        
                        if test['test_functions']:
                            f.write(f"- **Тестовые функции**:\n")
                            for func in test['test_functions']:
                                f.write(f"  - `{func['name']}`")
                                if func['description']:
                                    f.write(f": {func['description']}")
                                f.write("\n")
                        
                        f.write("\n")
    
    print(f"Документация сохранена в: {doc_file}")
    
    # Генерируем индекс
    index_file = tests_dir / 'TESTS_INDEX.md'
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write("# Индекс тестов EvilEye\n\n")
        f.write("Краткий индекс всех тестов по модулям.\n\n")
        
        for test_type in sorted(by_type.keys()):
            f.write(f"## {test_type.upper()} тесты\n\n")
            
            for category in sorted(by_type[test_type].keys()):
                f.write(f"### {category}\n\n")
                
                for subcategory in sorted(by_type[test_type][category].keys()):
                    if subcategory != 'general':
                        f.write(f"#### {subcategory}\n\n")
                    
                    tests = by_type[test_type][category][subcategory]
                    for test in sorted(tests, key=lambda x: x['name']):
                        f.write(f"- `{test['name']}`")
                        if test['description']:
                            desc = test['description'].split('\n')[0][:80]
                            f.write(f" - {desc}")
                        f.write("\n")
                
                f.write("\n")
    
    print(f"Индекс сохранен в: {index_file}")
    
    # Генерируем отчет о покрытии
    coverage_file = tests_dir / 'TESTS_COVERAGE.md'
    with open(coverage_file, 'w', encoding='utf-8') as f:
        f.write("# Покрытие модулей тестами\n\n")
        f.write("Статистика покрытия модулей тестами.\n\n")
        
        # Группируем по модулям
        by_module = defaultdict(list)
        for test in all_tests:
            module = test['module'] or 'unknown'
            by_module[module].append(test)
        
        f.write("## По модулям\n\n")
        for module in sorted(by_module.keys()):
            tests = by_module[module]
            f.write(f"### {module}\n\n")
            f.write(f"Тестов: {len(tests)}\n\n")
            for test in sorted(tests, key=lambda x: x['name']):
                f.write(f"- `{test['name']}` ({test['type'] or 'unknown'})\n")
            f.write("\n")
        
        # Статистика по типам
        f.write("## Статистика по типам\n\n")
        type_stats = defaultdict(int)
        for test in all_tests:
            test_type = test['type'] or 'unknown'
            type_stats[test_type] += 1
        
        for test_type, count in sorted(type_stats.items()):
            f.write(f"- **{test_type}**: {count}\n")
        
        # Статистика по категориям
        f.write("\n## Статистика по категориям\n\n")
        category_stats = defaultdict(int)
        for test in all_tests:
            category = test['category'] or 'unknown'
            category_stats[category] += 1
        
        for category, count in sorted(category_stats.items()):
            f.write(f"- **{category}**: {count}\n")
    
    print(f"Отчет о покрытии сохранен в: {coverage_file}")

if __name__ == '__main__':
    generate_documentation()

