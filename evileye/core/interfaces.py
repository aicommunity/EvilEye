"""Типовые контракты (Protocols) для компонентов EvilEye.

Этот модуль определяет интерфейсы через Python Protocols для использования
в type hints и статической проверке типов. Protocols не требуют явного
наследования и используются только для type checking.

Важные принципы:
- Protocols используются ТОЛЬКО для type hints и документации API
- НЕ требуют явного наследования (в отличие от ABC)
- НЕ используются для runtime проверок наследования
- Реализация обеспечивается через соответствие структуре методов

Связь с EvilEyeBase:
- `EvilEyeBase` - это runtime-фреймворк (lifecycle, plugin registry, logging)
- Protocols - это типовые контракты (type checking, документация)
- Классы, наследующиеся от `EvilEyeBase`, автоматически соответствуют Protocols
  если реализуют все необходимые методы

Пример использования:
    def process_pipeline(pipeline: IPipeline) -> None:
        # type checker знает, что pipeline имеет методы init(), process() и т.д.
        pipeline.init()
        result = pipeline.process()
    
    # PipelineBase автоматически соответствует IPipeline
    my_pipeline = PipelineSurveillance()  # наследуется от PipelineBase
    process_pipeline(my_pipeline)  # type checker не выдает ошибок
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IPipeline(Protocol):
    """Интерфейс для всех реализаций pipeline.

    Основан на уже существующем `PipelineBase`, но не навязывает наследование.
    Используется как контракт между контроллером, API и реализациями pipeline.
    """

    # Жизненный цикл
    def init(self, **kwargs: Any) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reset(self) -> None: ...

    # Конфигурация
    def set_params(self, **params: Any) -> None: ...

    def get_params(self) -> Dict[str, Any]: ...

    def set_credentials(self, credentials: Dict[str, Any]) -> None: ...

    def get_credentials(self) -> Optional[Dict[str, Any]]: ...

    # Основная обработка
    def process(self) -> Dict[str, Any]: ...

    # Доступ к источникам и результатам
    def get_sources(self) -> List[Any]: ...

    def get_results_list(self) -> List[Dict[str, Any]]: ...

    def get_current_results(self) -> Dict[str, Any]: ...


@runtime_checkable
class IObjectHandler(Protocol):
    """Интерфейс обработчика объектов.

    Основан на `ObjectsHandler`, но не требует прямого наследования.

    Связь с EvilEyeBase:
    ---------------------
    Классы, реализующие этот интерфейс, обычно наследуются от `EvilEyeBase`
    для получения lifecycle методов (init, release, reset) и логирования.

    Пример использования:
        def configure_handler(handler: IObjectHandler) -> None:
            handler.init()
            handler.set_params(**config)
        
        # ObjectsHandler автоматически соответствует IObjectHandler
        obj_handler = ObjectsHandler()
        configure_handler(obj_handler)  # type checker проверяет соответствие
    """

    # Жизненный цикл
    def init(self, **kwargs: Any) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reset(self) -> None: ...

    # Конфигурация
    def set_params(self, **params: Any) -> None: ...

    def get_params(self) -> Dict[str, Any]: ...

    # Основное API
    def put(self, data: Dict[str, Any]) -> None: ...

    def get(self, objs_type: str, cam_id: int) -> Any: ...

    def subscribe(self, *subscribers: Any) -> None: ...


@runtime_checkable
class IEventDetector(Protocol):
    """Интерфейс детектора событий (одного типа).
    
    Связь с EvilEyeBase:
    ---------------------
    Детекторы событий обычно наследуются от `EvilEyeBase` для получения
    lifecycle методов и логирования. Соответствие Protocol обеспечивается
    автоматически при реализации всех методов интерфейса.
    
    Пример использования:
        def process_events(detector: IEventDetector) -> List[Any]:
            detector.init()
            detector.start()
            events = list(detector.get())
            return events
    """

    # Жизненный цикл
    def init(self, **kwargs: Any) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reset(self) -> None: ...

    # Основное API
    def put(self, data: Any) -> None: ...

    def get(self) -> Iterable[Any]: ...

    def get_name(self) -> str: ...


@runtime_checkable
class IDatabaseAdapter(Protocol):
    """Интерфейс адаптера БД / JSON хранилища."""

    # Жизненный цикл
    def init(self, **kwargs: Any) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reset(self) -> None: ...

    # Конфигурация
    def set_params(self, **params: Any) -> None: ...

    def get_params(self) -> Dict[str, Any]: ...

    # Операции записи
    def insert(self, data: Dict[str, Any]) -> None: ...

    def update(self, data: Dict[str, Any]) -> None: ...

    # Метаданные
    def get_table_name(self) -> Optional[str]: ...

    def get_event_name(self) -> Optional[str]: ...


@runtime_checkable
class IVisualizer(Protocol):
    """Интерфейс визуализатора.
    
    Связь с EvilEyeBase:
    ---------------------
    Визуализатор обычно наследуется от `EvilEyeBase` для получения lifecycle методов.
    Соответствие Protocol обеспечивается автоматически при реализации всех методов.
    
    Пример использования:
        def update_visualization(visualizer: IVisualizer, frames: List[Any]) -> None:
            visualizer.init()
            visualizer.update(frames, {}, [], [], {})
    """

    # Жизненный цикл
    def init(self, **kwargs: Any) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reset(self) -> None: ...

    # Конфигурация
    def set_params(self, **params: Any) -> None: ...

    def get_params(self) -> Dict[str, Any]: ...

    # Основное API
    def update(
        self,
        processing_frames: List[Any],
        source_last_processed_frame_id: Dict[int, int],
        objects: List[Any],
        dropped_frames: List[Any],
        debug_info: Dict[str, Any],
    ) -> None: ...

    def set_signal_params(self, enabled: bool, color_rgb: tuple[int, int, int]) -> None: ...

