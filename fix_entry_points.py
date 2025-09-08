#!/usr/bin/env python3
"""
Python script to fix EvilEye entry points automatically
"""

import os
import sys
from pathlib import Path


def find_project_root():
    """
    Найти корневую папку проекта EvilEye.
    Ищет папку, содержащую pyproject.toml с именем проекта 'evileye'.
    """
    current_path = Path(__file__).resolve()
    
    # Поднимаемся по иерархии папок, ища pyproject.toml
    for parent in current_path.parents:
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            try:
                # Проверяем, что это действительно проект EvilEye
                content = pyproject_path.read_text()
                if "name = \"evileye\"" in content or "name = 'evileye'" in content:
                    return parent
            except Exception:
                continue
    
    # Если не нашли pyproject.toml, ищем по наличию папки evileye и файлов проекта
    for parent in current_path.parents:
        evileye_dir = parent / "evileye"
        if evileye_dir.exists() and evileye_dir.is_dir():
            # Проверяем, что это действительно папка с кодом проекта
            init_file = evileye_dir / "__init__.py"
            if init_file.exists():
                return parent
    
    # Если ничего не нашли, возвращаем папку, где находится этот скрипт
    return current_path.parent


def create_entry_point(name, wrapper_script):
    """Create or update an entry point script"""
    entry_points_dir = Path.home() / ".local" / "bin"
    entry_points_dir.mkdir(parents=True, exist_ok=True)
    
    entry_point_path = entry_points_dir / name
    
    # Get the project root directory using robust detection
    project_root = find_project_root()
    wrapper_path = project_root / "evileye" / wrapper_script
    
    entry_point_content = f'''#!/usr/bin/python
import sys
import os
import subprocess
from pathlib import Path

def find_project_root():
    """
    Найти корневую папку проекта EvilEye.
    Ищет папку, содержащую pyproject.toml с именем проекта 'evileye'.
    """
    # Начинаем поиск с текущей рабочей директории
    current_path = Path.cwd()
    
    # Поднимаемся по иерархии папок, ища pyproject.toml
    for parent in [current_path] + list(current_path.parents):
        pyproject_path = parent / "pyproject.toml"
        if pyproject_path.exists():
            try:
                # Проверяем, что это действительно проект EvilEye
                content = pyproject_path.read_text()
                if "name = \\"evileye\\"" in content or "name = 'evileye'" in content:
                    return parent
            except Exception:
                continue
    
    # Если не нашли pyproject.toml, ищем по наличию папки evileye и файлов проекта
    for parent in [current_path] + list(current_path.parents):
        evileye_dir = parent / "evileye"
        if evileye_dir.exists() and evileye_dir.is_dir():
            # Проверяем, что это действительно папка с кодом проекта
            init_file = evileye_dir / "__init__.py"
            if init_file.exists():
                return parent
    
    # Если ничего не нашли, пробуем найти в стандартных местах
    possible_paths = [
        Path.home() / "EvilEye",
        Path.home() / "evileye", 
        Path("/opt/evileye"),
        Path("/usr/local/evileye")
    ]
    
    for path in possible_paths:
        if path.exists():
            evileye_dir = path / "evileye"
            if evileye_dir.exists() and (evileye_dir / "__init__.py").exists():
                return path
    
    # Если ничего не нашли, возвращаем текущую рабочую директорию
    return current_path

# Get the project root directory using robust detection
project_root = find_project_root()

# Add project root to Python path
if project_root.exists():
    sys.path.insert(0, str(project_root))

# Try to import and run the wrapper directly
try:
    from evileye.{wrapper_script.replace('.py', '')} import main
    sys.exit(main())
except ImportError:
    # If import fails, try to execute wrapper script directly
    wrapper_path = project_root / "evileye" / "{wrapper_script}"
    
    if wrapper_path.exists():
        # Execute the wrapper script directly
        sys.argv[0] = str(wrapper_path)
        exec(wrapper_path.read_text(), {{
            '__name__': '__main__',
            '__file__': str(wrapper_path)
        }})
    else:
        print(f"Error: Could not find wrapper script at {{wrapper_path}}")
        sys.exit(1)
'''
    
    # Write the entry point
    entry_point_path.write_text(entry_point_content)
    entry_point_path.chmod(0o755)
    
    return entry_point_path


def fix_entry_points():
    """Fix all EvilEye entry points"""
    print("🔧 Fixing EvilEye entry points...")
    
    entry_points = {
        "evileye": "cli_wrapper.py",
        "evileye-process": "process_wrapper.py", 
        "evileye-configure": "configure_wrapper.py",
        "evileye-launch": "launch_wrapper.py",
        "evileye-create": "create_wrapper.py"
    }
    
    success_count = 0
    
    for name, wrapper in entry_points.items():
        try:
            entry_point_path = create_entry_point(name, wrapper)
            print(f"✅ Created: {entry_point_path}")
            success_count += 1
        except Exception as e:
            print(f"❌ Failed to create {name}: {e}")
    
    if success_count == len(entry_points):
        print("\n🎉 All entry points have been fixed!")
        print("\nYou can now use:")
        for name in entry_points.keys():
            print(f"  {name} --help")
    else:
        print(f"\n⚠️  Fixed {success_count}/{len(entry_points)} entry points")
    
    return success_count == len(entry_points)


def main():
    """Main function"""
    try:
        return fix_entry_points()
    except Exception as e:
        print(f"❌ Error fixing entry points: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
