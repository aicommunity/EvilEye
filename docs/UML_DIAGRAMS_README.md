# 🎨 UML Diagrams for EvilEye System

This document describes all the UML diagrams generated for the EvilEye computer vision system.

> **См. также**: [Архитектура системы](ARCHITECTURE.md) - Детальное описание архитектуры на 7 уровнях абстракции с интерактивными Mermaid диаграммами, которые дополняют статические UML диаграммы, описанные в этом документе.

## 📊 Generated Diagrams

### 1. **Class Diagrams**

#### Basic Class Diagram (`evileye_class_diagram.png`)
- **Size**: 662 KB
- **Description**: Basic class diagram showing all classes with their attributes and methods
- **Features**: Simple layout, all classes visible

#### Enhanced Class Diagram (`evileye_enhanced_class_diagram.png`)
- **Size**: 562 KB
- **Description**: Enhanced class diagram with color-coded packages and relationship analysis
- **Features**: 
  - Color-coded by package (Core, Objects Handler, Visualization, etc.)
  - Relationship analysis (inheritance, composition, aggregation)
  - Better styling and layout
  - 63 classes analyzed, 16 relationships found

#### Package Diagram (`evileye_package_diagram.png`)
- **Size**: 178 KB
- **Description**: Shows classes grouped by their packages
- **Features**: Hierarchical organization by module

### 2. **Architecture Diagrams**

#### System Architecture (`evileye_architecture.png`)
- **Size**: 81 KB
- **Description**: High-level system architecture showing the layered structure
- **Layers**:
  - **Input Layer**: Video Sources, Configuration Files
  - **Core Processing Layer**: Pipeline Base, System Controller
  - **Object Processing Layer**: Objects Handler, Labeling Manager
  - **Event Detection Layer**: FOV Detector, Zone Detector
  - **Output Layer**: Events Journal, File Storage

> **Дополнительные схемы архитектуры**: См. [Архитектура системы](ARCHITECTURE.md) для интерактивных Mermaid диаграмм на разных уровнях абстракции:
> - [Уровень 1: CLI и точки входа](ARCHITECTURE.md#уровень-1-cli-и-точки-входа)
> - [Уровень 2: Контроллер и основные сущности](ARCHITECTURE.md#уровень-2-контроллер-и-основные-сущности)
> - [Уровень 3: Pipeline архитектура](ARCHITECTURE.md#уровень-3-pipeline-архитектура)
> - [Уровень 4: Видеозахват и запись](ARCHITECTURE.md#уровень-4-видеозахват-и-запись)
> - [Уровень 5: Обработка объектов](ARCHITECTURE.md#уровень-5-обработка-объектов)
> - [Уровень 6: Обработка событий](ARCHITECTURE.md#уровень-6-обработка-событий)
> - [Уровень 7: Работа с базой данных](ARCHITECTURE.md#уровень-7-работа-с-базой-данных)

### 3. **Data Flow Diagrams**

#### Data Flow (`evileye_data_flow.png`)
- **Size**: 79 KB
- **Description**: Shows how data flows through the system
- **Flow**:
  - Video Frames → Pipeline Processing → Object Detection → Object Tracking
  - Object Data → JSON Files, Image Files, Database (optional)
  - Data → Events Journal with Image Previews

> **Детальные схемы потоков данных**: См. [Архитектура системы](ARCHITECTURE.md) для интерактивных диаграмм последовательности и потоков данных:
> - [Поток данных в главном цикле](ARCHITECTURE.md#поток-данных-в-главном-цикле)
> - [Процесс обработки PipelineSurveillance](ARCHITECTURE.md#процесс-обработки)
> - [Обработка результатов трекинга](ARCHITECTURE.md#обработка-результатов-трекинга)
> - [Поток сохранения данных](ARCHITECTURE.md#поток-сохранения-данных)

### 4. **PlantUML Diagrams**

#### PlantUML Class Diagram (`evileye_plantuml.puml`)
- **Size**: 15 KB
- **Description**: PlantUML source code for class diagram
- **Usage**: Can be viewed in VS Code with PlantUML extension or online at plantuml.com

#### Sequence Diagram (`evileye_sequence.puml`)
- **Size**: 1.5 KB
- **Description**: Main detection workflow sequence
- **Shows**: System initialization, video processing loop, object detection events

#### Component Diagram (`evileye_component.puml`)
- **Size**: 1.1 KB
- **Description**: System components and their relationships
- **Shows**: Core components, external dependencies, optional database connections

## 🚀 How to Generate

### Prerequisites
```bash
pip install graphviz plantuml
sudo apt install graphviz  # On Ubuntu/Debian
```

### Basic Generation
```bash
python generate_uml_diagrams.py
```

### Enhanced Generation
```bash
python generate_enhanced_uml.py
```

## 🎯 Key System Components

### Core Package
- **PipelineBase**: Base class for all pipeline implementations
- **EvilEyeBase**: Base class for all system components

### Objects Handler Package
- **ObjectsHandler**: Manages object detection and tracking
- **LabelingManager**: Handles saving object labels to JSON files

### Visualization Package
- **EventsJournalJson**: JSON-based event journal GUI
- **JsonLabelJournalDataSource**: Provides data to JSON journal from disk

### Controller Package
- **Controller**: Orchestrates the pipeline and its components

### Events Detectors Package
- **EventFOV**: Field of View event detection
- **EventZone**: Zone-based event detection

## 🔗 Key Relationships

### Inheritance
- `PipelineBase` extends `EvilEyeBase`
- `ObjectsHandler` extends `EvilEyeBase`
- `LabelingManager` extends `EvilEyeBase`

### Composition
- `ObjectsHandler` has `LabelingManager`
- `Controller` has `PipelineBase`
- `Controller` has `ObjectsHandler`

### Aggregation
- `ObjectsHandler` uses `EventFOV` and `EventZone`
- `EventsJournalJson` uses `JsonLabelJournalDataSource`

## 🎨 Color Coding

- **🔵 Core**: Light Blue (#E3F2FD)
- **🟢 Objects Handler**: Light Green (#E8F5E8)
- **🟡 Visualization**: Light Yellow (#FFF8E1)
- **🔴 Controller**: Light Red (#FFEBEE)
- **🟣 Events Detectors**: Light Purple (#F3E5F5)

## 📈 System Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐
│   Input Layer   │    │ Video Sources   │
│                 │    │ Configuration   │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          ▼                      ▼
┌─────────────────────────────────────────┐
│         Core Processing Layer           │
│  Pipeline Base  │  System Controller   │
└─────────┬───────┴─────────┬─────────────┘
          │                 │
          ▼                 ▼
┌─────────────────┐    ┌─────────────────┐
│Object Processing│    │Event Detection  │
│Objects Handler  │    │FOV & Zone      │
│Labeling Manager │    │Detectors        │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          ▼                      ▼
┌─────────────────────────────────────────┐
│           Output Layer                  │
│  Events Journal  │  File Storage       │
└─────────────────────────────────────────┘
```

## 🔄 Data Flow

```
Video Frame → Pipeline → Detection → Tracking
    ↓           ↓          ↓         ↓
Config Data    Processed   Detected   Object Data
    ↓           Frames     Objects    ↓
    └───────────→ └────────→ └────────┘
                           ↓
                    ┌─────────────────┐
                    │   Storage       │
                    │JSON │ Images │DB│
                    └─────────┬───────┘
                              ↓
                    ┌─────────────────┐
                    │  Events Journal │
                    │  (GUI Display)  │
                    └─────────────────┘
```

## 💡 Usage Tips

### Viewing Diagrams
1. **PNG files**: Open in any image viewer
2. **PlantUML files**: Use VS Code extension or online viewer
3. **Large diagrams**: Zoom in to see details

### Modifying Diagrams
1. Edit the Python generator scripts
2. Modify PlantUML source files
3. Regenerate using the scripts

### Customization
- Change colors in `package_colors` dictionary
- Modify class analysis in `analyze_class` method
- Add new diagram types in generator classes

## 🎯 Benefits

### For Developers
- **Understanding**: Clear view of system architecture
- **Documentation**: Visual representation of code structure
- **Maintenance**: Easy to identify relationships and dependencies
- **Complementary**: Static UML diagrams complement interactive Mermaid diagrams in [ARCHITECTURE.md](ARCHITECTURE.md)

### For Architects
- **Design Review**: Validate system design decisions
- **Scalability**: Identify potential bottlenecks
- **Integration**: Plan new feature integration
- **Multi-level View**: Combine static UML with [multi-level architecture diagrams](ARCHITECTURE.md)

### For Stakeholders
- **Communication**: Visual explanation of system complexity
- **Planning**: Resource allocation and timeline estimation
- **Risk Assessment**: Identify critical system components

## 🔮 Future Enhancements

### Planned Features
- **Runtime Analysis**: Dynamic relationship detection
- **Performance Metrics**: Memory usage and execution time
- **Dependency Graphs**: Import/export relationships
- **Interactive Diagrams**: Clickable elements with details

### Integration Possibilities
- **CI/CD**: Automatic diagram generation on code changes
- **Documentation**: Integration with Sphinx or MkDocs
- **Monitoring**: Real-time system state visualization

---

**Generated**: September 3, 2025  
**System**: EvilEye Computer Vision System  
**Total Classes**: 63  
**Total Relationships**: 16  
**Diagram Types**: 8 (5 PNG + 3 PlantUML)
