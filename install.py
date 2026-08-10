#!/usr/bin/env python3
"""
Installation script for EvilEye package with automatic entry point fixing
"""

import subprocess
import sys
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
    fix_script_py = Path("scripts/setup/fix_entry_points.py")
    if not fix_script_py.is_file():
        fix_script_py = Path("fix_entry_points.py")

    if fix_script_py.exists():
        return run_command(f"python {fix_script_py}", "Fixing entry points with Python script")
    print("⚠️  fix_entry_points.py not found, skipping entry point fix")
    return True


def main():
    """Main installation function"""
    print("🚀 EvilEye Installation Script")
    print("=" * 40)

    extra_deps = None
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--dev":
            extra_deps = "dev"
        elif arg == "--win":
            extra_deps = "win"
        elif arg == "--jetson":
            extra_deps = "jetson"
        elif arg == "--help":
            print("Usage: python install.py [--dev|--win|--jetson]")
            print("  --dev     - Install with development dependencies")
            print("  --win     - Install Windows optional extra (onnxruntime pin)")
            print("  --jetson  - Install Jetson optional extra (PyQt5)")
            return
        else:
            print(f"Unknown option: {arg} (use --help)")
            sys.exit(2)

    if not install_package(extra_deps):
        print("❌ Installation failed!")
        sys.exit(1)

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


if __name__ == "__main__":
    main()
