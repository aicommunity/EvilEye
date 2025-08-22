#!/usr/bin/env python3
"""
Python script to fix EvilEye entry points automatically
"""

import os
import sys
from pathlib import Path


def create_entry_point(name, wrapper_script):
    """Create or update an entry point script"""
    entry_points_dir = Path.home() / ".local" / "bin"
    entry_points_dir.mkdir(parents=True, exist_ok=True)
    
    entry_point_path = entry_points_dir / name
    
    # Get the project root directory
    project_root = Path(__file__).parent
    wrapper_path = project_root / "evileye" / wrapper_script
    
    entry_point_content = f'''#!/usr/bin/python
import sys
import os
import subprocess
from pathlib import Path

# Get the project root directory
project_root = Path(__file__).parent.parent.parent / "EvilEye"

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
        "evileye-gui": "gui_wrapper.py",
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
