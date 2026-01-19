#!/usr/bin/env python3
"""
UML Diagram Generator for EvilEye System
Generates various UML diagrams based on the codebase structure.
"""

import os
import ast
import inspect
import importlib
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
import graphviz
import plantuml

class UMLGenerator:
    """Generates UML diagrams from Python code."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.evileye_root = self.project_root / "evileye"
        self.classes = {}
        self.relationships = []
        self.packages = {}
        
    def analyze_project(self):
        """Analyze the entire project structure."""
        print("🔍 Analyzing EvilEye project structure...")
        
        # Analyze core modules
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
        
        print(f"✅ Analyzed {len(self.classes)} classes")
        print(f"✅ Found {len(self.relationships)} relationships")
        
    def analyze_module(self, module_name: str):
        """Analyze a specific module."""
        try:
            module = importlib.import_module(module_name)
            self.analyze_module_classes(module, module_name)
        except ImportError as e:
            print(f"⚠️ Could not import {module_name}: {e}")
    
    def analyze_module_classes(self, module, module_name: str):
        """Analyze classes in a module."""
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj):
                class_info = self.analyze_class(obj, module_name)
                if class_info:
                    self.classes[name] = class_info
    
    def analyze_class(self, cls, module_name: str) -> Optional[Dict]:
        """Analyze a single class."""
        try:
            # Get class attributes
            attributes = []
            methods = []
            
            # Analyze class attributes
            for attr_name, attr_value in cls.__dict__.items():
                if not attr_name.startswith('_'):
                    attr_type = type(attr_value).__name__
                    attributes.append({
                        'name': attr_name,
                        'type': attr_type,
                        'visibility': 'private' if attr_name.startswith('_') else 'public'
                    })
            
            # Analyze methods
            for method_name, method_obj in inspect.getmembers(cls, inspect.isfunction):
                if not method_name.startswith('_'):
                    methods.append({
                        'name': method_name,
                        'visibility': 'public'
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
                'docstring': cls.__doc__ or ''
            }
        except Exception as e:
            print(f"⚠️ Error analyzing class {cls.__name__}: {e}")
            return None
    
    def generate_class_diagram(self, output_file: str = "evileye_class_diagram"):
        """Generate a class diagram using Graphviz."""
        print("🎨 Generating class diagram...")
        
        dot = graphviz.Digraph(comment='EvilEye Class Diagram')
        dot.attr(rankdir='TB')
        
        # Add classes
        for class_name, class_info in self.classes.items():
            # Create class box
            class_label = f"{{ {class_name} |"
            
            # Add attributes
            if class_info['attributes']:
                class_label += "\\l".join([f"- {attr['name']}: {attr['type']}" 
                                         for attr in class_info['attributes'][:5]]) + "\\l |"
            else:
                class_label += "\\l |"
            
            # Add methods
            if class_info['methods']:
                method_names = [f"+ {method['name']}" for method in class_info['methods'][:5]]
                class_label += "\\l".join(method_names) + "\\l"
            else:
                class_label += "\\l"
            
            class_label += " }"
            
            # Color by package
            package_colors = {
                'core': 'lightblue',
                'objects_handler': 'lightgreen', 
                'visualization_modules': 'lightyellow',
                'controller': 'lightcoral',
                'events_detectors': 'lightpink'
            }
            color = package_colors.get(class_info['package'], 'white')
            
            dot.node(class_name, class_label, 
                    shape='record', 
                    style='filled', 
                    fillcolor=color)
        
        # Add inheritance relationships
        for class_name, class_info in self.classes.items():
            for base in class_info['bases']:
                if base in self.classes:
                    dot.edge(base, class_name, arrowhead='empty')
        
        # Save diagram
        dot.render(output_file, format='png', cleanup=True)
        print(f"✅ Class diagram saved as {output_file}.png")
        
        return dot
    
    def generate_package_diagram(self, output_file: str = "evileye_package_diagram"):
        """Generate a package diagram."""
        print("📦 Generating package diagram...")
        
        dot = graphviz.Digraph(comment='EvilEye Package Diagram')
        dot.attr(rankdir='LR')
        
        # Group classes by package
        packages = {}
        for class_name, class_info in self.classes.items():
            package = class_info['package']
            if package not in packages:
                packages[package] = []
            packages[package].append(class_name)
        
        # Create package nodes
        for package_name, classes in packages.items():
            with dot.subgraph(name=f'cluster_{package_name}') as c:
                c.attr(label=package_name, style='filled', fillcolor='lightgray')
                for class_name in classes:
                    c.node(class_name, class_name, shape='box')
        
        # Save diagram
        dot.render(output_file, format='png', cleanup=True)
        print(f"✅ Package diagram saved as {output_file}.png")
        
        return dot
    
    def generate_plantuml_class_diagram(self, output_file: str = "evileye_plantuml.puml"):
        """Generate PlantUML class diagram code."""
        print("🌱 Generating PlantUML class diagram...")
        
        plantuml_code = "@startuml\n"
        plantuml_code += "!theme plain\n"
        plantuml_code += "skinparam classAttributeIconSize 0\n"
        plantuml_code += "skinparam classFontSize 10\n"
        plantuml_code += "skinparam classFontName Arial\n\n"
        
        # Add classes
        for class_name, class_info in self.classes.items():
            plantuml_code += f"class {class_name} {{\n"
            
            # Add attributes
            for attr in class_info['attributes'][:8]:  # Limit attributes
                visibility = "-" if attr['visibility'] == 'private' else "+"
                plantuml_code += f"  {visibility} {attr['name']}: {attr['type']}\n"
            
            # Add methods
            for method in class_info['methods'][:8]:  # Limit methods
                visibility = "-" if method['visibility'] == 'private' else "+"
                plantuml_code += f"  {visibility} {method['name']}\n"
            
            plantuml_code += "}\n\n"
        
        # Add inheritance relationships
        for class_name, class_info in self.classes.items():
            for base in class_info['bases']:
                if base in self.classes:
                    plantuml_code += f"{base} <|-- {class_name}\n"
        
        plantuml_code += "@enduml\n"
        
        # Save PlantUML file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(plantuml_code)
        
        print(f"✅ PlantUML diagram saved as {output_file}")
        
        return plantuml_code
    
    def generate_sequence_diagram(self, output_file: str = "evileye_sequence.puml"):
        """Generate a sequence diagram for the main workflow."""
        print("⏱️ Generating sequence diagram...")
        
        sequence_code = """@startuml
!theme plain
skinparam sequenceArrowThickness 2
skinparam roundcorner 20
skinparam maxmessagesize 60

title EvilEye System - Main Detection Workflow

actor User
participant Controller
participant Pipeline
participant ObjectsHandler
participant LabelingManager
participant EventsJournal

User -> Controller: Start System
activate Controller

Controller -> Pipeline: Initialize
activate Pipeline

Controller -> ObjectsHandler: Initialize
activate ObjectsHandler

ObjectsHandler -> LabelingManager: Initialize
activate LabelingManager

LabelingManager -> LabelingManager: Load Existing Data
LabelingManager -> ObjectsHandler: Return Max Object ID
ObjectsHandler -> ObjectsHandler: Set Object Counter

Controller -> Pipeline: Start Processing
activate Pipeline

loop Video Processing
    Pipeline -> ObjectsHandler: Process Frame
    ObjectsHandler -> ObjectsHandler: Detect Objects
    
    alt New Object Found
        ObjectsHandler -> ObjectsHandler: Assign Object ID
        ObjectsHandler -> LabelingManager: Save Found Object
        ObjectsHandler -> EventsJournal: Update Journal
    end
    
    alt Object Lost
        ObjectsHandler -> LabelingManager: Save Lost Object
        ObjectsHandler -> EventsJournal: Update Journal
    end
end

User -> Controller: Stop System
Controller -> Pipeline: Stop
Controller -> ObjectsHandler: Stop
Controller -> LabelingManager: Stop
Controller -> EventsJournal: Close

deactivate Pipeline
deactivate ObjectsHandler
deactivate LabelingManager
deactivate EventsJournal
deactivate Controller

@enduml
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(sequence_code)
        
        print(f"✅ Sequence diagram saved as {output_file}")
        return sequence_code
    
    def generate_component_diagram(self, output_file: str = "evileye_component.puml"):
        """Generate a component diagram."""
        print("🔧 Generating component diagram...")
        
        component_code = """@startuml
!theme plain
skinparam componentStyle rectangle

package "EvilEye System" {
    
    package "Core" {
        [PipelineBase] as Pipeline
        [BaseClass] as Base
    }
    
    package "Object Handling" {
        [ObjectsHandler] as Handler
        [LabelingManager] as Labeling
    }
    
    package "Visualization" {
        [EventsJournalJson] as Journal
        [JsonLabelJournalDataSource] as DataSource
    }
    
    package "Detection" {
        [EventFOV] as FOV
        [EventZone] as Zone
    }
    
    package "Control" {
        [Controller] as Ctrl
    }
    
    package "External" {
        [Video Source] as Video
        [File System] as FS
        [Database] as DB
    }
    
    ' Relationships
    Video --> Pipeline
    Pipeline --> Handler
    Handler --> Labeling
    Handler --> Journal
    Journal --> DataSource
    DataSource --> FS
    Labeling --> FS
    Handler --> FOV
    Handler --> Zone
    Ctrl --> Pipeline
    Ctrl --> Handler
    Ctrl --> Journal
    
    ' Database connections (optional)
    Handler ..> DB : <<optional>>
    Journal ..> DB : <<optional>>
}

@enduml
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(component_code)
        
        print(f"✅ Component diagram saved as {output_file}")
        return component_code
    
    def generate_all_diagrams(self):
        """Generate all UML diagrams."""
        print("🚀 Starting UML diagram generation...")
        
        # Analyze project
        self.analyze_project()
        
        # Generate diagrams
        self.generate_class_diagram()
        self.generate_package_diagram()
        self.generate_plantuml_class_diagram()
        self.generate_sequence_diagram()
        self.generate_component_diagram()
        
        print("\n🎯 All UML diagrams generated successfully!")
        print("\n📁 Generated files:")
        print("  • evileye_class_diagram.png - Class diagram (Graphviz)")
        print("  • evileye_package_diagram.png - Package diagram (Graphviz)")
        print("  • evileye_plantuml.puml - PlantUML class diagram")
        print("  • evileye_sequence.puml - Sequence diagram")
        print("  • evileye_component.puml - Component diagram")
        print("\n💡 To view PlantUML diagrams:")
        print("  • Use PlantUML extension in VS Code")
        print("  • Or visit: http://www.plantuml.com/plantuml/uml/")

def main():
    """Main function to generate all UML diagrams."""
    generator = UMLGenerator()
    generator.generate_all_diagrams()

if __name__ == "__main__":
    main()
