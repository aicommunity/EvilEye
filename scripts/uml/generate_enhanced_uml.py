#!/usr/bin/env python3
"""
Enhanced UML Diagram Generator for EvilEye System
Creates detailed and beautiful UML diagrams with better analysis.
"""

import os
import inspect
import importlib
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
import graphviz

class EnhancedUMLGenerator:
    """Enhanced UML diagram generator with better analysis."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.evileye_root = self.project_root / "evileye"
        self.classes = {}
        self.relationships = []
        self.packages = {}
        
    def analyze_project(self):
        """Analyze the entire project structure with enhanced details."""
        print("🔍 Analyzing EvilEye project structure...")
        
        # Core modules to analyze
        core_modules = [
            "evileye.core.pipeline_base",
            "evileye.core.base_class", 
            "evileye.objects_handler.objects_handler",
            "evileye.objects_handler.labeling_manager",
            "evileye.visualization_modules.events_journal_json",
            "evileye.visualization_modules.journal_data_source_json",
            "evileye.controller.controller",
            "evileye.events_detectors.event_fov",
            "evileye.events_detectors.event_zone"
        ]
        
        for module_name in core_modules:
            try:
                self.analyze_module(module_name)
            except Exception as e:
                print(f"⚠️ Warning: Could not analyze {module_name}: {e}")
        
        # Analyze relationships
        self.analyze_relationships()
        
        print(f"✅ Analyzed {len(self.classes)} classes")
        print(f"✅ Found {len(self.relationships)} relationships")
        
    def analyze_module(self, module_name: str):
        """Analyze a specific module with enhanced class analysis."""
        try:
            module = importlib.import_module(module_name)
            self.analyze_module_classes(module, module_name)
        except ImportError as e:
            print(f"⚠️ Could not import {module_name}: {e}")
    
    def analyze_module_classes(self, module, module_name: str):
        """Analyze classes in a module with detailed information."""
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj):
                class_info = self.analyze_class(obj, module_name)
                if class_info:
                    self.classes[name] = class_info
    
    def analyze_class(self, cls, module_name: str) -> Optional[Dict]:
        """Analyze a single class with enhanced details."""
        try:
            # Get class attributes
            attributes = []
            methods = []
            
            # Analyze class attributes
            for attr_name, attr_value in cls.__dict__.items():
                if not attr_name.startswith('__'):
                    attr_type = type(attr_value).__name__
                    visibility = 'private' if attr_name.startswith('_') else 'public'
                    
                    # Get more specific type information
                    if hasattr(attr_value, '__class__'):
                        attr_type = attr_value.__class__.__name__
                    
                    attributes.append({
                        'name': attr_name,
                        'type': attr_type,
                        'visibility': visibility,
                        'value': str(attr_value)[:50] if attr_value else None
                    })
            
            # Analyze methods
            for method_name, method_obj in inspect.getmembers(cls, inspect.isfunction):
                if not method_name.startswith('__'):
                    # Get method signature
                    try:
                        sig = inspect.signature(method_obj)
                        params = [f"{name}: {param.annotation.__name__ if param.annotation != inspect.Parameter.empty else 'Any'}" 
                                for name, param in sig.parameters.items() if name != 'self']
                        method_signature = f"{method_name}({', '.join(params)})"
                    except:
                        method_signature = f"{method_name}()"
                    
                    methods.append({
                        'name': method_name,
                        'signature': method_signature,
                        'visibility': 'public',
                        'docstring': method_obj.__doc__ or ''
                    })
            
            # Get base classes
            bases = [base.__name__ for base in cls.__bases__ if base.__name__ != 'object']
            
            # Get package info
            package = module_name.split('.')[1] if len(module_name.split('.')) > 1 else 'core'
            
            return {
                'name': cls.__name__,
                'module': module_name,
                'package': package,
                'bases': bases,
                'attributes': attributes,
                'methods': methods,
                'docstring': cls.__doc__ or '',
                'abstract': inspect.isabstract(cls)
            }
        except Exception as e:
            print(f"⚠️ Error analyzing class {cls.__name__}: {e}")
            return None
    
    def analyze_relationships(self):
        """Analyze relationships between classes."""
        for class_name, class_info in self.classes.items():
            # Inheritance relationships
            for base in class_info['bases']:
                if base in self.classes:
                    self.relationships.append({
                        'type': 'inheritance',
                        'from': base,
                        'to': class_name,
                        'label': 'extends'
                    })
            
            # Composition/aggregation relationships (based on attributes)
            for attr in class_info['attributes']:
                if attr['type'] in self.classes:
                    # Check if it's composition (strong ownership) or aggregation
                    if attr['name'].startswith('_'):
                        rel_type = 'composition'
                    else:
                        rel_type = 'aggregation'
                    
                    self.relationships.append({
                        'type': rel_type,
                        'from': class_name,
                        'to': attr['type'],
                        'label': f"has {attr['name']}"
                    })
    
    def generate_enhanced_class_diagram(self, output_file: str = "evileye_enhanced_class_diagram"):
        """Generate an enhanced class diagram with better styling."""
        print("🎨 Generating enhanced class diagram...")
        
        dot = graphviz.Digraph(comment='EvilEye Enhanced Class Diagram')
        dot.attr(rankdir='TB', 
                fontname='Arial', 
                fontsize='12',
                nodesep='0.5',
                ranksep='0.8')
        
        # Color scheme
        package_colors = {
            'core': '#E3F2FD',           # Light Blue
            'objects_handler': '#E8F5E8', # Light Green
            'visualization_modules': '#FFF8E1', # Light Yellow
            'controller': '#FFEBEE',      # Light Red
            'events_detectors': '#F3E5F5' # Light Purple
        }
        
        # Add classes with enhanced styling
        for class_name, class_info in self.classes.items():
            # Create class box with better formatting
            class_label = self.create_class_label(class_info)
            
            # Get color for package
            color = package_colors.get(class_info['package'], '#FFFFFF')
            
            # Add node with enhanced styling
            dot.node(class_name, class_label, 
                    shape='record', 
                    style='filled,rounded', 
                    fillcolor=color,
                    fontname='Arial',
                    fontsize='10',
                    margin='0.2')
        
        # Add relationships with different styles
        for rel in self.relationships:
            if rel['type'] == 'inheritance':
                dot.edge(rel['from'], rel['to'], 
                        arrowhead='empty', 
                        arrowsize='1.5',
                        penwidth='2',
                        color='#1976D2')
            elif rel['type'] == 'composition':
                dot.edge(rel['from'], rel['to'], 
                        arrowhead='diamond', 
                        arrowsize='1.5',
                        penwidth='1.5',
                        color='#D32F2F',
                        label=rel['label'])
            elif rel['type'] == 'aggregation':
                dot.edge(rel['from'], rel['to'], 
                        arrowhead='odiamond', 
                        arrowsize='1.5',
                        penwidth='1.5',
                        color='#FF8F00',
                        label=rel['label'])
        
        # Save diagram
        dot.render(output_file, format='png', cleanup=True)
        print(f"✅ Enhanced class diagram saved as {output_file}.png")
        
        return dot
    
    def create_class_label(self, class_info: Dict) -> str:
        """Create a formatted class label for the diagram."""
        label = f"{{ {class_info['name']} |"
        
        # Add attributes section
        if class_info['attributes']:
            # Show only important attributes
            important_attrs = [attr for attr in class_info['attributes'] 
                             if not attr['name'].startswith('__')][:6]
            
            for attr in important_attrs:
                visibility = "-" if attr['visibility'] == 'private' else "+"
                attr_type = attr['type'] if attr['type'] != 'NoneType' else 'Any'
                label += f"\\l{visibility} {attr['name']}: {attr_type}"
        else:
            label += "\\l"
        
        label += "\\l |"
        
        # Add methods section
        if class_info['methods']:
            # Show only important methods
            important_methods = [method for method in class_info['methods'] 
                               if not method['name'].startswith('__')][:6]
            
            for method in important_methods:
                visibility = "-" if method['visibility'] == 'private' else "+"
                method_name = method['name']
                label += f"\\l{visibility} {method_name}()"
        else:
            label += "\\l"
        
        label += "\\l }"
        return label
    
    def generate_architecture_diagram(self, output_file: str = "evileye_architecture"):
        """Generate a high-level architecture diagram."""
        print("🏗️ Generating architecture diagram...")
        
        dot = graphviz.Digraph(comment='EvilEye System Architecture')
        dot.attr(rankdir='TB', 
                fontname='Arial', 
                fontsize='14',
                nodesep='1.0',
                ranksep='1.2')
        
        # Define system layers
        with dot.subgraph(name='cluster_input') as c:
            c.attr(label='Input Layer', style='filled', fillcolor='#E1F5FE', fontsize='16')
            c.node('Video', 'Video Sources\n(Cameras, Files)', 
                   shape='box', style='filled', fillcolor='#81D4FA')
            c.node('Config', 'Configuration\nFiles', 
                   shape='box', style='filled', fillcolor='#81D4FA')
        
        with dot.subgraph(name='cluster_core') as c:
            c.attr(label='Core Processing Layer', style='filled', fillcolor='#F3E5F5', fontsize='16')
            c.node('Pipeline', 'Pipeline\nBase', 
                   shape='box', style='filled', fillcolor='#BA68C8')
            c.node('Controller', 'System\nController', 
                   shape='box', style='filled', fillcolor='#BA68C8')
        
        with dot.subgraph(name='cluster_processing') as c:
            c.attr(label='Object Processing Layer', style='filled', fillcolor='#E8F5E8', fontsize='16')
            c.node('Handler', 'Objects\nHandler', 
                   shape='box', style='filled', fillcolor='#81C784')
            c.node('Labeling', 'Labeling\nManager', 
                   shape='box', style='filled', fillcolor='#81C784')
        
        with dot.subgraph(name='cluster_detection') as c:
            c.attr(label='Event Detection Layer', style='filled', fillcolor='#FFF3E0', fontsize='16')
            c.node('FOV', 'FOV\nDetector', 
                   shape='box', style='filled', fillcolor='#FFB74D')
            c.node('Zone', 'Zone\nDetector', 
                   shape='box', style='filled', fillcolor='#FFB74D')
        
        with dot.subgraph(name='cluster_output') as c:
            c.attr(label='Output Layer', style='filled', fillcolor='#FFEBEE', fontsize='16')
            c.node('Journal', 'Events\nJournal', 
                   shape='box', style='filled', fillcolor='#F48FB1')
            c.node('Storage', 'File\nStorage', 
                   shape='box', style='filled', fillcolor='#F48FB1')
        
        # Add relationships
        dot.edge('Video', 'Pipeline', arrowhead='normal', penwidth='2')
        dot.edge('Config', 'Controller', arrowhead='normal', penwidth='2')
        dot.edge('Controller', 'Pipeline', arrowhead='normal', penwidth='2')
        dot.edge('Pipeline', 'Handler', arrowhead='normal', penwidth='2')
        dot.edge('Handler', 'Labeling', arrowhead='normal', penwidth='2')
        dot.edge('Handler', 'FOV', arrowhead='normal', penwidth='2')
        dot.edge('Handler', 'Zone', arrowhead='normal', penwidth='2')
        dot.edge('Handler', 'Journal', arrowhead='normal', penwidth='2')
        dot.edge('Labeling', 'Storage', arrowhead='normal', penwidth='2')
        dot.edge('Journal', 'Storage', arrowhead='normal', penwidth='2')
        
        # Save diagram
        dot.render(output_file, format='png', cleanup=True)
        print(f"✅ Architecture diagram saved as {output_file}.png")
        
        return dot
    
    def generate_data_flow_diagram(self, output_file: str = "evileye_data_flow"):
        """Generate a data flow diagram."""
        print("🌊 Generating data flow diagram...")
        
        dot = graphviz.Digraph(comment='EvilEye Data Flow')
        dot.attr(rankdir='LR', 
                fontname='Arial', 
                fontsize='12',
                nodesep='1.0',
                ranksep='1.5')
        
        # Data sources
        dot.node('Video', 'Video Frame', shape='oval', style='filled', fillcolor='#E3F2FD')
        dot.node('Config', 'Config Data', shape='oval', style='filled', fillcolor='#E3F2FD')
        
        # Processing nodes
        dot.node('Pipeline', 'Pipeline\nProcessing', shape='box', style='filled', fillcolor='#F3E5F5')
        dot.node('Detection', 'Object\nDetection', shape='box', style='filled', fillcolor='#E8F5E8')
        dot.node('Tracking', 'Object\nTracking', shape='box', style='filled', fillcolor='#E8F5E8')
        
        # Data storage
        dot.node('JSON', 'JSON\nFiles', shape='cylinder', style='filled', fillcolor='#FFF3E0')
        dot.node('Images', 'Image\nFiles', shape='cylinder', style='filled', fillcolor='#FFF3E0')
        dot.node('DB', 'Database\n(Optional)', shape='cylinder', style='filled', fillcolor='#FFEBEE')
        
        # Output
        dot.node('Journal', 'Events\nJournal', shape='box', style='filled', fillcolor='#FCE4EC')
        
        # Data flow
        dot.edge('Video', 'Pipeline', label='Raw Frames', penwidth='2')
        dot.edge('Config', 'Pipeline', label='Settings', penwidth='2')
        dot.edge('Pipeline', 'Detection', label='Processed Frames', penwidth='2')
        dot.edge('Detection', 'Tracking', label='Detected Objects', penwidth='2')
        dot.edge('Tracking', 'JSON', label='Object Data', penwidth='2')
        dot.edge('Tracking', 'Images', label='Object Images', penwidth='2')
        dot.edge('Tracking', 'DB', label='Object Records', penwidth='2', style='dashed')
        dot.edge('JSON', 'Journal', label='Event Data', penwidth='2')
        dot.edge('Images', 'Journal', label='Image Previews', penwidth='2')
        
        # Save diagram
        dot.render(output_file, format='png', cleanup=True)
        print(f"✅ Data flow diagram saved as {output_file}.png")
        
        return dot
    
    def generate_all_enhanced_diagrams(self):
        """Generate all enhanced UML diagrams."""
        print("🚀 Starting enhanced UML diagram generation...")
        
        # Analyze project
        self.analyze_project()
        
        # Generate diagrams
        self.generate_enhanced_class_diagram()
        self.generate_architecture_diagram()
        self.generate_data_flow_diagram()
        
        print("\n🎯 All enhanced UML diagrams generated successfully!")
        print("\n📁 Generated files:")
        print("  • evileye_enhanced_class_diagram.png - Enhanced class diagram")
        print("  • evileye_architecture.png - System architecture diagram")
        print("  • evileye_data_flow.png - Data flow diagram")
        print("\n💡 Features:")
        print("  • Color-coded packages")
        print("  • Relationship analysis")
        print("  • Enhanced styling")
        print("  • Architecture overview")

def main():
    """Main function to generate enhanced UML diagrams."""
    generator = EnhancedUMLGenerator()
    generator.generate_all_enhanced_diagrams()

if __name__ == "__main__":
    main()
