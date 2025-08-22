#!/usr/bin/env python3
"""
EvilEye Configuration Creator

This script creates new configuration files for the EvilEye surveillance system.
"""

import argparse
import json
import sys
import os
from pathlib import Path

# Add project root to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from evileye.controller import controller


def create_args_parser():
    """Create argument parser for the create script"""
    parser = argparse.ArgumentParser(
        description="Create new EvilEye configuration file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  evileye-create my_config              # Create configs/my_config.json
  evileye-create configs/custom.json    # Create specific path
  evileye-create --sources 2            # Create config with 2 sources
  evileye-create --template basic       # Use basic template
        """
    )
    
    parser.add_argument(
        'config_name',
        nargs='?',
        type=str,
        help="Name of the configuration file (without .json extension)"
    )
    
    parser.add_argument(
        '--sources',
        type=int,
        default=0,
        help="Number of video sources to include in the configuration (default: 0)"
    )
    
    parser.add_argument(
        '--template',
        choices=['basic', 'full', 'minimal'],
        default='basic',
        help="Configuration template to use (default: basic)"
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='configs',
        help="Output directory for configuration files (default: configs)"
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help="Overwrite existing configuration file"
    )
    
    parser.add_argument(
        '--list-templates',
        action='store_true',
        help="List available configuration templates"
    )
    
    return parser


def list_templates():
    """List available configuration templates"""
    templates = {
        'basic': {
            'description': 'Basic configuration with minimal settings',
            'sources': 1,
            'features': ['detection', 'tracking']
        },
        'full': {
            'description': 'Full configuration with all features enabled',
            'sources': 2,
            'features': ['detection', 'tracking', 'multi-camera', 'database', 'events']
        },
        'minimal': {
            'description': 'Minimal configuration for testing',
            'sources': 0,
            'features': ['detection']
        }
    }
    
    print("Available configuration templates:")
    print("=" * 50)
    
    for name, info in templates.items():
        print(f"\n{name.upper()}:")
        print(f"  Description: {info['description']}")
        print(f"  Sources: {info['sources']}")
        print(f"  Features: {', '.join(info['features'])}")
    
    print("\nUse --template <name> to specify a template when creating a configuration.")


def create_config_file(config_name, sources=0, template='basic', output_dir='configs', force=False):
    """Create a new configuration file"""
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Determine output file path
    if config_name is None:
        config_name = f"new_config_{template}"
    
    if not config_name.endswith('.json'):
        config_name += '.json'
    
    output_path = os.path.join(output_dir, config_name)
    
    # Check if file already exists
    if os.path.exists(output_path) and not force:
        print(f"❌ Configuration file '{output_path}' already exists!")
        print(f"   Use --force to overwrite or choose a different name.")
        return False
    
    # Create controller instance and generate configuration
    print(f"🔧 Creating configuration with template: {template}")
    print(f"   Sources: {sources}")
    print(f"   Output: {output_path}")
    
    try:
        controller_instance = controller.Controller()
        config_data = controller_instance.create_config(num_sources=sources, pipeline_class=None)
        
        # Apply template-specific modifications
        if template == 'full':
            # Enable all features
            config_data.setdefault('database', {})
            config_data.setdefault('events_detectors', {})
            config_data.setdefault('objects_handler', {})
            
        elif template == 'minimal':
            # Disable optional features
            config_data.pop('database', None)
            config_data.pop('events_detectors', None)
            config_data.pop('objects_handler', None)
        
        # Write configuration to file
        with open(output_path, 'w') as f:
            json.dump(config_data, f, indent=4)
        
        print(f"✅ Configuration created successfully!")
        print(f"   File: {output_path}")
        print(f"   Size: {os.path.getsize(output_path)} bytes")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating configuration: {e}")
        return False


def main():
    """Main entry point for the configuration creator"""
    parser = create_args_parser()
    args = parser.parse_args()
    
    # Handle list templates
    if args.list_templates:
        list_templates()
        return 0
    
    # Validate arguments
    if args.config_name is None:
        print("❌ Configuration name is required!")
        print("   Usage: evileye-create <config_name>")
        print("   Use --help for more information.")
        return 1
    
    # Create configuration
    success = create_config_file(
        config_name=args.config_name,
        sources=args.sources,
        template=args.template,
        output_dir=args.output_dir,
        force=args.force
    )
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
