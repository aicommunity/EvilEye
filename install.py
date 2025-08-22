#!/usr/bin/env python3
"""
Installation script for EvilEye package with automatic entry point fixing
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"   Command: {cmd}")
        print(f"   Error: {e.stderr}")
        return False


def install_package(extra_deps=None):
    """Install the package with optional extra dependencies"""
    if extra_deps:
        cmd = f"pip install -e .[{extra_deps}]"
        description = f"Installing package with {extra_deps} dependencies"
    else:
        cmd = "pip install -e ."
        description = "Installing package"
    
    return run_command(cmd, description)


def fix_entry_points():
    """Fix entry points after installation"""
    # Use Python script for fixing entry points
    fix_script_py = Path("fix_entry_points.py")
    
    if fix_script_py.exists():
        return run_command(f"python {fix_script_py}", "Fixing entry points with Python script")
    else:
        print("⚠️  fix_entry_points.py not found, skipping entry point fix")
        return True


def main():
    """Main installation function"""
    print("🚀 EvilEye Installation Script")
    print("=" * 40)
    
    # Parse command line arguments
    extra_deps = None
    if len(sys.argv) > 1:
        if sys.argv[1] == "--dev":
            extra_deps = "dev"
        elif sys.argv[1] == "--full":
            extra_deps = "full"
        elif sys.argv[1] == "--gui":
            extra_deps = "gui"
        elif sys.argv[1] == "--gpu":
            extra_deps = "gpu"
        elif sys.argv[1] == "--help":
            print("Usage: python install.py [--dev|--full|--gui|--gpu]")
            print("  --dev   - Install with development dependencies")
            print("  --full  - Install with all dependencies")
            print("  --gui   - Install with GUI dependencies")
            print("  --gpu   - Install with GPU support")
            return
    
    # Install package
    if not install_package(extra_deps):
        print("❌ Installation failed!")
        sys.exit(1)
    
    # Fix entry points
    if not fix_entry_points():
        print("⚠️  Entry point fix failed, but installation completed")
    
    print("\n🎉 Installation completed successfully!")
    print("\nYou can now use:")
    print("  evileye --help")
    print("  evileye info")
    print("  evileye-process --help")
    
    if extra_deps == "dev":
        print("\nDevelopment tools available:")
        print("  make test     - Run tests")
        print("  make lint     - Run linting")
        print("  make format   - Format code")


def auto_fix_entry_points():
    """Auto-fix entry points without user interaction"""
    try:
        # Import the package to trigger auto-fix
        import evileye
        return True
    except Exception as e:
        print(f"⚠️  Auto-fix failed: {e}")
        return False


if __name__ == "__main__":
    main()
else:
    # If imported as module, auto-fix entry points
    auto_fix_entry_points()


def auto_fix_entry_points():
    """Auto-fix entry points without user interaction"""
    try:
        # Import the package to trigger auto-fix
        import evileye
        return True
    except Exception as e:
        print(f"⚠️  Auto-fix failed: {e}")
        return False


if __name__ == "__main__":
    main()
else:
    # If imported as module, auto-fix entry points
    auto_fix_entry_points()


if __name__ == "__main__":
    main()
