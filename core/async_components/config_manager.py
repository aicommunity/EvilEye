import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from pathlib import Path
import yaml


@dataclass
class ProcessorConfig:
    """Конфигурация процессора"""
    name: str
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    max_queue_size: int = 10
    timeout: float = 0.1
    batch_size: int = 1
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessorConfig':
        return cls(**data)


@dataclass
class PipelineConfig:
    """Конфигурация pipeline"""
    name: str
    processors: List[ProcessorConfig] = field(default_factory=list)
    enabled: bool = True
    max_concurrent_tasks: int = 4
    buffer_size: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'enabled': self.enabled,
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'buffer_size': self.buffer_size,
            'processors': [p.to_dict() for p in self.processors]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PipelineConfig':
        processors = [ProcessorConfig.from_dict(p) for p in data.get('processors', [])]
        return cls(
            name=data['name'],
            processors=processors,
            enabled=data.get('enabled', True),
            max_concurrent_tasks=data.get('max_concurrent_tasks', 4),
            buffer_size=data.get('buffer_size', 100)
        )


@dataclass
class SystemConfig:
    """Системная конфигурация"""
    fps: int = 30
    max_memory_usage_mb: int = 16384
    memory_check_interval_sec: int = 900
    auto_restart: bool = True
    debug_mode: bool = False
    log_level: str = "INFO"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SystemConfig':
        return cls(**data)


class ConfigManager:
    """
    Менеджер конфигурации для централизованного управления настройками.
    Поддерживает загрузку из JSON и YAML файлов.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config_data: Dict[str, Any] = {}
        self.pipelines: Dict[str, PipelineConfig] = {}
        self.processors: Dict[str, ProcessorConfig] = {}
        self.system_config = SystemConfig()
        
        if config_path:
            self.load_config(config_path)
    
    def load_config(self, config_path: str):
        """Загрузка конфигурации из файла"""
        self.config_path = config_path
        path = Path(config_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                self.config_data = yaml.safe_load(f)
            else:
                self.config_data = json.load(f)
        
        self._parse_config()
        print(f"Configuration loaded from: {config_path}")
    
    def save_config(self, config_path: Optional[str] = None):
        """Сохранение конфигурации в файл"""
        if config_path is None:
            config_path = self.config_path
        
        if config_path is None:
            raise ValueError("No config path specified")
        
        path = Path(config_path)
        
        # Подготовка данных для сохранения
        save_data = {
            'system': self.system_config.to_dict(),
            'pipelines': {name: pipeline.to_dict() for name, pipeline in self.pipelines.items()},
            'processors': {name: processor.to_dict() for name, processor in self.processors.items()}
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                yaml.dump(save_data, f, default_flow_style=False, indent=2)
            else:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        print(f"Configuration saved to: {config_path}")
    
    def _parse_config(self):
        """Парсинг загруженной конфигурации"""
        # Системная конфигурация
        system_data = self.config_data.get('system', {})
        self.system_config = SystemConfig.from_dict(system_data)
        
        # Конфигурации процессоров
        processors_data = self.config_data.get('processors', {})
        for name, data in processors_data.items():
            if isinstance(data, dict):
                processor_config = ProcessorConfig.from_dict(data)
                processor_config.name = name
                self.processors[name] = processor_config
        
        # Конфигурации pipeline
        pipelines_data = self.config_data.get('pipelines', {})
        for name, data in pipelines_data.items():
            if isinstance(data, dict):
                pipeline_config = PipelineConfig.from_dict(data)
                pipeline_config.name = name
                self.pipelines[name] = pipeline_config
    
    def get_processor_config(self, name: str) -> Optional[ProcessorConfig]:
        """Получение конфигурации процессора"""
        return self.processors.get(name)
    
    def get_pipeline_config(self, name: str) -> Optional[PipelineConfig]:
        """Получение конфигурации pipeline"""
        return self.pipelines.get(name)
    
    def add_processor_config(self, name: str, config: ProcessorConfig):
        """Добавление конфигурации процессора"""
        config.name = name
        self.processors[name] = config
    
    def add_pipeline_config(self, name: str, config: PipelineConfig):
        """Добавление конфигурации pipeline"""
        config.name = name
        self.pipelines[name] = config
    
    def remove_processor_config(self, name: str):
        """Удаление конфигурации процессора"""
        if name in self.processors:
            del self.processors[name]
    
    def remove_pipeline_config(self, name: str):
        """Удаление конфигурации pipeline"""
        if name in self.pipelines:
            del self.pipelines[name]
    
    def get_enabled_processors(self) -> Dict[str, ProcessorConfig]:
        """Получение всех включенных процессоров"""
        return {name: config for name, config in self.processors.items() if config.enabled}
    
    def get_enabled_pipelines(self) -> Dict[str, PipelineConfig]:
        """Получение всех включенных pipeline"""
        return {name: config for name, config in self.pipelines.items() if config.enabled}
    
    def validate_config(self) -> List[str]:
        """Валидация конфигурации"""
        errors = []
        
        # Проверка процессоров
        for name, config in self.processors.items():
            if not config.name:
                errors.append(f"Processor {name}: missing name")
            if config.max_queue_size <= 0:
                errors.append(f"Processor {name}: invalid max_queue_size")
            if config.timeout <= 0:
                errors.append(f"Processor {name}: invalid timeout")
        
        # Проверка pipeline
        for name, config in self.pipelines.items():
            if not config.name:
                errors.append(f"Pipeline {name}: missing name")
            if config.max_concurrent_tasks <= 0:
                errors.append(f"Pipeline {name}: invalid max_concurrent_tasks")
            
            # Проверка зависимостей процессоров
            for processor in config.processors:
                for dep in processor.dependencies:
                    if dep not in self.processors:
                        errors.append(f"Pipeline {name}, processor {processor.name}: missing dependency {dep}")
        
        # Проверка системной конфигурации
        if self.system_config.fps <= 0:
            errors.append("System: invalid fps")
        if self.system_config.max_memory_usage_mb <= 0:
            errors.append("System: invalid max_memory_usage_mb")
        
        return errors
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Получение сводки конфигурации"""
        return {
            'system': self.system_config.to_dict(),
            'processors_count': len(self.processors),
            'enabled_processors_count': len(self.get_enabled_processors()),
            'pipelines_count': len(self.pipelines),
            'enabled_pipelines_count': len(self.get_enabled_pipelines()),
            'validation_errors': self.validate_config()
        }
    
    def create_default_config(self) -> Dict[str, Any]:
        """Создание конфигурации по умолчанию"""
        return {
            'system': {
                'fps': 30,
                'max_memory_usage_mb': 16384,
                'memory_check_interval_sec': 900,
                'auto_restart': True,
                'debug_mode': False,
                'log_level': 'INFO'
            },
            'processors': {
                'video_capture': {
                    'type': 'VideoCapture',
                    'enabled': True,
                    'max_queue_size': 5,
                    'timeout': 0.1,
                    'params': {
                        'fps': 30,
                        'resolution': [1920, 1080]
                    }
                },
                'object_detector': {
                    'type': 'ObjectDetectorYolo',
                    'enabled': True,
                    'max_queue_size': 10,
                    'timeout': 0.1,
                    'batch_size': 1,
                    'dependencies': ['video_capture'],
                    'params': {
                        'model': 'yolo11n.pt',
                        'confidence': 0.25,
                        'device': 'cpu'
                    }
                },
                'object_tracker': {
                    'type': 'ObjectTrackingBotsort',
                    'enabled': True,
                    'max_queue_size': 10,
                    'timeout': 0.1,
                    'dependencies': ['object_detector'],
                    'params': {
                        'tracker_onnx': 'osnet_ain_x1_0_M.onnx'
                    }
                }
            },
            'pipelines': {
                'surveillance': {
                    'enabled': True,
                    'max_concurrent_tasks': 4,
                    'buffer_size': 100,
                    'processors': [
                        {'name': 'video_capture'},
                        {'name': 'object_detector'},
                        {'name': 'object_tracker'}
                    ]
                }
            }
        }
    
    def export_config(self, format: str = 'json') -> str:
        """Экспорт конфигурации в строку"""
        export_data = {
            'system': self.system_config.to_dict(),
            'pipelines': {name: pipeline.to_dict() for name, pipeline in self.pipelines.items()},
            'processors': {name: processor.to_dict() for name, processor in self.processors.items()}
        }
        
        if format.lower() == 'yaml':
            return yaml.dump(export_data, default_flow_style=False, indent=2)
        else:
            return json.dumps(export_data, indent=2, ensure_ascii=False)
