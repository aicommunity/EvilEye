"""
Ядро системы EvilEye (evileye/core).

Этот модуль предоставляет базовую инфраструктуру для компонентов системы:

- **EvilEyeBase**: Runtime-фреймворк для компонентов с lifecycle (init/release, plugin registry, logging)
- **interfaces.py**: Типовые контракты (Protocols) для type hints и документации API
- **base_class.py**: Базовый класс для всех компонентов системы
- **pipeline_base.py**: Базовый класс для всех реализаций pipeline
- **processor_base.py**: Базовый класс для процессоров pipeline
- **logger.py**: Утилиты для логирования (get_module_logger для модулей без lifecycle)

Разделение ответственности:
- EvilEyeBase — runtime-фреймворк (lifecycle, plugin registry, logging)
- interfaces.py — типовые контракты (type checking, документация API)
- DIContainer/DependencyRegistry — зарезервировано для будущего использования

См. также: docs/ARCHITECTURE.md раздел "Дополнительные паттерны: DI и фасады"
"""

from .base_class import EvilEyeBase
from .frame import CaptureImage, Frame
from .processor_base import ProcessorBase
from .processor_source import ProcessorSource
from .processor_step import ProcessorStep
from .processor_frame import ProcessorFrame
from .mp_worker import MpWorker
from .mp_control import MpControl
from .pipeline_processors import PipelineProcessors
from .pipeline_base import PipelineBase
from .pipeline_simple import PipelineSimple
from .interfaces import (
    IDatabaseAdapter,
    IEventDetector,
    IObjectHandler,
    IPipeline,
    IVisualizer,
)
from .contracts import (
    ControllerContext,
    DatabaseConfig,
    DatabaseDependencies,
    EventsConfig,
    EventsDependencies,
    PipelineConfig,
    PipelineDependencies,
    VisualizationConfig,
    VisualizationDependencies,
)
from .facades import DatabaseFacade, PipelineFacade
# DI компоненты: зарезервировано для будущего использования
# В текущей версии используется EvilEyeBase._registry как основной механизм создания компонентов
from .di_container import DIContainer
from .dependencies import DependencyRegistry, DependencyDefinition, get_registry, register_dependency
from .config_validator import ConfigValidator
from .object_pool import ObjectPool

