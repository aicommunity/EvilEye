import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import time
from pathlib import Path

from core.async_components import (
    ServiceContainer, EventBus, ConfigManager, 
    AsyncProcessorBase, Frame, DetectionResult, TrackingResult
)
from pipelines.async_pipelines import AsyncPipelineSurveillance
from core import EvilEyeBase

# Импорты для совместимости с оригинальным Controller
from database_controller.database_controller_pg import DatabaseControllerPg
from database_controller.db_adapter_objects import DatabaseAdapterObjects
from database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents
from database_controller.db_adapter_fov_events import DatabaseAdapterFieldOfViewEvents
from database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from events_control.events_processor import EventsProcessor
from events_control.events_controller import EventsDetectorsController
from events_detectors.cam_events_detector import CamEventsDetector
from events_detectors.fov_events_detector import FieldOfViewEventsDetector
from events_detectors.zone_events_detector import ZoneEventsDetector
from objects_handler import objects_handler
from visualization_modules.visualizer import Visualizer

# Импорты для процессоров
import capture
import object_detector
import object_tracker
import preprocessing
import object_multi_camera_tracker


class AsyncController(EvilEyeBase):
    """
    Асинхронный контроллер с оптимизированной архитектурой.
    Использует event-driven подход и dependency injection.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        super().__init__()
        
        # Основные компоненты
        self.service_container = ServiceContainer()
        self.event_bus = EventBus()
        self.config_manager = ConfigManager(config_path)
        
        # Pipeline
        self.pipeline: Optional[AsyncPipelineSurveillance] = None
        
        # Состояние
        self.running = False
        self.initialized = False
        
        # Статистика
        self.stats = {
            'start_time': None,
            'total_frames_processed': 0,
            'total_events_processed': 0,
            'errors_count': 0,
            'uptime_seconds': 0
        }
        
        # Атрибуты для совместимости с оригинальным Controller
        self.main_window = None
        self.params = None
        self.credentials = dict()
        self.database_config = dict()
        self.source_id_name_table = dict()
        self.source_video_duration = dict()
        self.source_last_processed_frame_id = dict()
        
        # Компоненты pipeline (для совместимости)
        self.sources_proc = None
        self.preprocessors_proc = None
        self.detectors_proc = None
        self.trackers_proc = None
        self.mc_trackers_proc = None
        
        # Дополнительные компоненты
        self.obj_handler = None
        self.visualizer = None
        self.pyqt_slots = None
        self.pyqt_signals = None
        
        # Настройки контроллера
        self.fps = 30
        self._show_main_gui = True
        self._show_journal = False
        self._enable_close_from_gui = True
        self.memory_periodic_check_sec = 60*15
        self.max_memory_usage_mb = 1024*16
        self.auto_restart = True
        self.class_names = list()
        
        # Компоненты событий
        self.events_detectors_controller = None
        self.events_processor = None
        self.cam_events_detector = None
        self.fov_events_detector = None
        self.zone_events_detector = None
        
        # Компоненты базы данных
        self.db_controller = None
        self.db_adapter_obj = None
        self.db_adapter_cam_events = None
        self.db_adapter_fov_events = None
        self.db_adapter_zone_events = None
        
        # Флаги состояния
        self.run_flag = False
        self.restart_flag = False
        self.gui_enabled = True
        self.autoclose = False
        
        # Размеры GUI
        self.current_main_widget_size = [1920, 1080]
        
        # Отладочная информация
        self.debug_info = dict()
        
        # Загрузка конфигурации БД
        self._load_database_config()
        
        # Регистрация сервисов
        self._register_services()

    def _load_database_config(self):
        """Загрузка конфигурации базы данных для совместимости"""
        try:
            with open("database_config.json", 'r') as data_config_file:
                self.database_config = json.load(data_config_file)
        except FileNotFoundError:
            # Создаем базовую конфигурацию если файл не найден
            self.database_config = {
                "database": {
                    "tables": {},
                    "image_dir": "/home/user/EvilEyeData",
                    "create_new_project": False,
                    "preview_width": 300,
                    "preview_height": 150,
                    "user_name": "postgres",
                    "password": "",
                    "database_name": "evil_eye_db",
                    "host_name": "localhost",
                    "port": 5432,
                    "default_database_name": "postgres",
                    "default_password": "",
                    "default_user_name": "postgres",
                    "default_host_name": "localhost",
                    "default_port": 5432
                },
                "database_adapters": {
                    "DatabaseAdapterObjects": {"table_name": "objects"},
                    "DatabaseAdapterCamEvents": {"table_name": "camera_events", "event_name": "CameraEvent"},
                    "DatabaseAdapterFieldOfViewEvents": {"table_name": "fov_events"},
                    "DatabaseAdapterZoneEvents": {"table_name": "zone_events"}
                }
            }
            print("Warning: database_config.json not found, using default configuration")

    def _init_db_controller(self, params, system_params):
        """Инициализация контроллера базы данных"""
        # Добавляем недостающие поля с значениями по умолчанию
        default_params = {
            "user_name": "postgres",
            "password": "",
            "database_name": "evil_eye_db",
            "host_name": "localhost",
            "port": 5432,
            "default_database_name": "postgres",
            "default_password": "",
            "default_user_name": "postgres",
            "default_host_name": "localhost",
            "default_port": 5432
        }
        
        # Объединяем с переданными параметрами
        db_params = {**default_params, **params}
        
        self.db_controller = DatabaseControllerPg(system_params)
        self.db_controller.set_params(**db_params)
        self.db_controller.init()

    def _init_db_adapters(self, params):
        """Инициализация адаптеров базы данных"""
        # Добавляем недостающие адаптеры с значениями по умолчанию
        default_adapters = {
            "DatabaseAdapterObjects": {"table_name": "objects"},
            "DatabaseAdapterCamEvents": {"table_name": "camera_events", "event_name": "CameraEvent"},
            "DatabaseAdapterFieldOfViewEvents": {"table_name": "fov_events"},
            "DatabaseAdapterZoneEvents": {"table_name": "zone_events"}
        }
        
        # Объединяем с переданными параметрами
        adapter_params = {**default_adapters, **params}
        
        self.db_adapter_obj = DatabaseAdapterObjects(self.db_controller)
        self.db_adapter_obj.set_params(**adapter_params['DatabaseAdapterObjects'])
        self.db_adapter_obj.init()

        self.db_adapter_cam_events = DatabaseAdapterCamEvents(self.db_controller)
        self.db_adapter_cam_events.set_params(**adapter_params['DatabaseAdapterCamEvents'])
        self.db_adapter_cam_events.init()

        self.db_adapter_fov_events = DatabaseAdapterFieldOfViewEvents(self.db_controller)
        self.db_adapter_fov_events.set_params(**adapter_params['DatabaseAdapterFieldOfViewEvents'])
        self.db_adapter_fov_events.init()

        self.db_adapter_zone_events = DatabaseAdapterZoneEvents(self.db_controller)
        self.db_adapter_zone_events.set_params(**adapter_params['DatabaseAdapterZoneEvents'])
        self.db_adapter_zone_events.init()

    def _init_events_detectors(self, params):
        """Инициализация детекторов событий"""
        if self.pipeline and hasattr(self.pipeline, 'get_sources_processors'):
            sources_processors = self.pipeline.get_sources_processors()
        else:
            sources_processors = []
            
        self.cam_events_detector = CamEventsDetector(sources_processors)
        self.cam_events_detector.set_params(**params.get('CamEventsDetector', dict()))
        self.cam_events_detector.init()

        if self.obj_handler:
            self.fov_events_detector = FieldOfViewEventsDetector(self.obj_handler)
            self.fov_events_detector.set_params(**params.get('FieldOfViewEventsDetector', dict()))
            self.fov_events_detector.init()

            self.zone_events_detector = ZoneEventsDetector(self.obj_handler)
            self.zone_events_detector.set_params(**params.get('ZoneEventsDetector', dict()))
            self.zone_events_detector.init()

            self.obj_handler.subscribe(self.fov_events_detector, self.zone_events_detector)
            
        for source in sources_processors:
            source.subscribe(self.cam_events_detector)

    def _init_events_detectors_controller(self, params):
        """Инициализация контроллера детекторов событий"""
        detectors = [self.cam_events_detector, self.fov_events_detector, self.zone_events_detector]
        self.events_detectors_controller = EventsDetectorsController(detectors)
        self.events_detectors_controller.set_params(**params)
        self.events_detectors_controller.init()

    def _init_events_processor(self, params):
        """Инициализация процессора событий"""
        db_adapters = [self.db_adapter_fov_events, self.db_adapter_cam_events, self.db_adapter_zone_events]
        self.events_processor = EventsProcessor(db_adapters, self.db_controller)
        self.events_processor.set_params(**params)
        self.events_processor.init()

    def __init_object_handler(self, db_controller, params):
        """Инициализация обработчика объектов"""
        self.obj_handler = objects_handler.ObjectsHandler(db_controller=db_controller, db_adapter=self.db_adapter_obj)
        self.obj_handler.set_params(**params)
        self.obj_handler.init()

    def _init_visualizer(self, params):
        """Инициализация визуализатора"""
        self.gui_enabled = params.get("gui_enabled", True)
        self.visualizer = Visualizer(self.pyqt_slots, self.pyqt_signals)
        self.visualizer.set_params(**params)
        self.visualizer.source_id_name_table = self.source_id_name_table
        self.visualizer.source_video_duration = self.source_video_duration
        self.visualizer.init()
    
    def _register_services(self):
        """Регистрация сервисов в контейнере"""
        # Основные сервисы
        self.service_container.register('event_bus', self.event_bus)
        self.service_container.register('config_manager', self.config_manager)
        
        # Pipeline будет зарегистрирован после инициализации
        print("Services registered in container")
    
    async def initialize(self, pipeline_config: Optional[Dict[str, Any]] = None):
        """Инициализация контроллера"""
        if self.initialized:
            return
        
        try:
            # Сохраняем конфигурацию
            self.params = pipeline_config or {}
            
            # Валидация конфигурации
            config_errors = self.config_manager.validate_config()
            if config_errors:
                raise ValueError(f"Configuration errors: {config_errors}")
            
            # Создание и настройка pipeline
            await self._setup_pipeline(pipeline_config)
            
            # Регистрация pipeline в сервисном контейнере
            if self.pipeline:
                self.service_container.register('pipeline', self.pipeline)
            
            # Инициализация компонентов базы данных
            self._init_db_controller(self.database_config['database'], system_params=self.params)
            self._init_db_adapters(self.database_config['database_adapters'])
            
            # Инициализация обработчика объектов (после адаптеров БД)
            self.__init_object_handler(self.db_controller, self.params.get('objects_handler', dict()))
            
            # Инициализация детекторов событий
            self._init_events_detectors(self.params.get('events_detectors', dict()))
            self._init_events_detectors_controller(self.params.get('events_detectors', dict()))
            self._init_events_processor(self.params.get('events_processor', dict()))
            
            # Настройка параметров контроллера
            if 'controller' in self.params.keys():
                self.autoclose = self.params['controller'].get("autoclose", self.autoclose)
                self.fps = self.params['controller'].get("fps", self.fps)
                self.show_main_gui = self.params['controller'].get("show_main_gui", self.show_main_gui)
                self.show_journal = self.params['controller'].get("show_journal", self.show_journal)
                self.enable_close_from_gui = self.params['controller'].get("enable_close_from_gui", self.enable_close_from_gui)
                self.class_names = self.params['controller'].get("class_names", list())
                self.memory_periodic_check_sec = self.params['controller'].get("memory_periodic_check_sec", self.memory_periodic_check_sec)
                self.max_memory_usage_mb = self.params['controller'].get("max_memory_usage_mb", self.max_memory_usage_mb)
                self.auto_restart = self.params['controller'].get("auto_restart", self.auto_restart)
            
            # Подписка на события
            await self._setup_event_handlers()
            
            self.initialized = True
            print("AsyncController initialized successfully")
            
        except Exception as e:
            print(f"Error initializing AsyncController: {e}")
            raise
    
    async def _setup_pipeline(self, pipeline_config: Optional[Dict[str, Any]] = None):
        """Настройка pipeline"""
        # Получение конфигурации pipeline
        if pipeline_config:
            # Использование переданной конфигурации
            config_data = pipeline_config
        else:
            # Использование конфигурации по умолчанию
            config_data = self.config_manager.create_default_config()
        
        # Создание конфигурации pipeline
        from core.async_components.config_manager import PipelineConfig, ProcessorConfig
        
        # Создание процессоров на основе конфигурации
        processors = {}
        for name, proc_config_data in config_data.get('processors', {}).items():
            processor = await self._create_processor(name, proc_config_data)
            if processor:
                processors[name] = processor
        
        # Создание pipeline
        pipeline_config_obj = PipelineConfig(
            name=config_data.get('pipelines', {}).get('surveillance', {}).get('name', 'surveillance'),
            enabled=True,
            max_concurrent_tasks=4,
            buffer_size=100
        )
        
        self.pipeline = AsyncPipelineSurveillance(pipeline_config_obj)
        
        # Настройка процессоров в pipeline
        if 'video_capture' in processors:
            self.pipeline.setup_processors(
                capture_processor=processors['video_capture'],
                detection_processor=processors.get('object_detector'),
                tracking_processor=processors.get('object_tracker'),
                mc_tracking_processor=processors.get('mc_tracker')
            )
        
        # Настройка пулов моделей
        self.pipeline.setup_model_pools(
            detection_pool_size=2,
            tracking_pool_size=2
        )
        
        print("Pipeline setup completed")
    
    async def _create_processor(self, name: str, config: Dict[str, Any]) -> Optional[AsyncProcessorBase]:
        """Создание процессора на основе конфигурации"""
        processor_type = config.get('type', '')
        
        try:
            print(f"Creating processor: {name} of type {processor_type}")
            
            # Словарь соответствия типов процессоров и их классов
            processor_classes = {
                'VideoCapture': capture.VideoCapture,
                'ObjectDetectorYolo': object_detector.ObjectDetectorYolo,
                'ObjectDetectorYoloMp': object_detector.ObjectDetectorYoloMp,
                'ObjectTrackingBotsort': object_tracker.ObjectTrackingBotsort,
                'PreprocessingVehicle': preprocessing.PreprocessingVehicle,
                'ObjectMultiCameraTracking': object_multi_camera_tracker.ObjectMultiCameraTracking
            }
            
            # Получение класса процессора
            processor_class = processor_classes.get(processor_type)
            if not processor_class:
                print(f"Unknown processor type: {processor_type}")
                return None
            
            # Создание процессора с параметрами
            processor_params = config.get('params', {})
            processor = processor_class()
            
            # Установка параметров
            if hasattr(processor, 'set_params'):
                processor.set_params(**processor_params)
            
            # Инициализация процессора
            if hasattr(processor, 'init'):
                processor.init()
            
            print(f"Successfully created processor: {name} of type {processor_type}")
            return processor
            
        except Exception as e:
            print(f"Error creating processor {name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _setup_event_handlers(self):
        """Настройка обработчиков событий"""
        # Обработчик событий обработки кадров
        async def frame_processed_handler(event):
            self.stats['total_frames_processed'] += 1
            await self.event_bus.publish(
                'frame_processed', 
                event.data, 
                source='controller'
            )
        
        # Обработчик ошибок
        async def error_handler(event):
            self.stats['errors_count'] += 1
            print(f"Error event: {event.data}")
        
        # Обработчик метрик
        async def metrics_handler(event):
            # Публикация метрик каждые 30 секунд
            if self.stats['total_frames_processed'] % 30 == 0:
                await self._publish_metrics()
        
        # Подписка на события
        self.event_bus.subscribe('frame_processed', frame_processed_handler)
        self.event_bus.subscribe('error', error_handler)
        self.event_bus.subscribe('metrics_request', metrics_handler)
        
        print("Event handlers setup completed")
    
    async def start(self):
        """Запуск контроллера"""
        if not self.initialized:
            await self.initialize()
        
        if self.running:
            return
        
        try:
            # Запуск сервисов
            await self.service_container.start_all()
            
            # Запуск pipeline
            if self.pipeline:
                await self.pipeline.start()
            
            # Запуск задачи мониторинга
            asyncio.create_task(self._monitoring_task())
            
            self.running = True
            self.stats['start_time'] = datetime.now()
            
            print("AsyncController started successfully")
            
        except Exception as e:
            print(f"Error starting AsyncController: {e}")
            raise
    
    async def stop(self):
        """Остановка контроллера"""
        if not self.running:
            return
        
        self.running = False
        
        try:
            # Остановка pipeline
            if self.pipeline:
                await self.pipeline.stop()
            
            # Остановка сервисов
            await self.service_container.stop_all()
            
            # Обновление статистики
            if self.stats['start_time']:
                self.stats['uptime_seconds'] = (
                    datetime.now() - self.stats['start_time']
                ).total_seconds()
            
            print("AsyncController stopped successfully")
            
        except Exception as e:
            print(f"Error stopping AsyncController: {e}")
    
    async def _monitoring_task(self):
        """Задача мониторинга системы"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Проверка каждые 30 секунд
                
                # Проверка здоровья системы
                health = await self._check_system_health()
                
                # Публикация метрик
                await self._publish_metrics()
                
                # Обработка рекомендаций
                if self.pipeline:
                    recommendations = self.pipeline.get_performance_recommendations()
                    if recommendations:
                        await self.event_bus.publish(
                            'performance_recommendations',
                            recommendations,
                            source='monitoring'
                        )
                
            except Exception as e:
                print(f"Error in monitoring task: {e}")
    
    async def _check_system_health(self) -> Dict[str, Any]:
        """Проверка состояния системы"""
        health = {
            'controller_running': self.running,
            'pipeline_health': None,
            'services_health': {},
            'overall_health': 'healthy'
        }
        
        # Проверка pipeline
        if self.pipeline:
            pipeline_health = await self.pipeline.health_check()
            health['pipeline_health'] = pipeline_health
            
            if pipeline_health.get('overall_health') != 'healthy':
                health['overall_health'] = 'degraded'
        
        # Проверка сервисов
        for service_name in self.service_container.list_services():
            try:
                service = self.service_container.get(service_name)
                if hasattr(service, 'running'):
                    health['services_health'][service_name] = service.running
                else:
                    health['services_health'][service_name] = True
            except Exception:
                health['services_health'][service_name] = False
                health['overall_health'] = 'unhealthy'
        
        return health
    
    async def _publish_metrics(self):
        """Публикация метрик"""
        metrics = {
            'controller_stats': self.stats,
            'pipeline_metrics': None,
            'event_bus_stats': self.event_bus.get_statistics(),
            'timestamp': datetime.now().isoformat()
        }
        
        if self.pipeline:
            metrics['pipeline_metrics'] = self.pipeline.get_detailed_metrics()
        
        await self.event_bus.publish('metrics', metrics, source='controller')
    
    async def process_frame(self, frame: Frame) -> Optional[TrackingResult]:
        """Обработка одного кадра"""
        if not self.running or not self.pipeline:
            return None
        
        try:
            result = await self.pipeline.process_frame(frame)
            
            # Публикация события обработки кадра
            await self.event_bus.publish(
                'frame_processed',
                {'frame_id': frame.id, 'source_id': frame.source_id},
                source='controller'
            )
            
            return result
            
        except Exception as e:
            await self.event_bus.publish('error', str(e), source='controller')
            return None
    
    async def process_batch(self, frames: List[Frame]) -> List[TrackingResult]:
        """Батчевая обработка кадров"""
        if not self.running or not self.pipeline:
            return []
        
        try:
            results = await self.pipeline.process_batch_optimized(frames)
            
            # Публикация события батчевой обработки
            await self.event_bus.publish(
                'batch_processed',
                {'frames_count': len(frames), 'results_count': len(results)},
                source='controller'
            )
            
            return results
            
        except Exception as e:
            await self.event_bus.publish('error', str(e), source='controller')
            return []
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик контроллера"""
        return {
            'controller': self.stats,
            'pipeline': self.pipeline.get_detailed_metrics() if self.pipeline else None,
            'event_bus': self.event_bus.get_statistics(),
            'services': {
                name: self.service_container.get_service_info(name)
                for name in self.service_container.list_services()
            }
        }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Получение статуса здоровья системы"""
        return await self._check_system_health()
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Получение сводки конфигурации"""
        return self.config_manager.get_config_summary()
    
    async def update_config(self, new_config: Dict[str, Any]):
        """Обновление конфигурации"""
        # Валидация новой конфигурации
        temp_config_manager = ConfigManager()
        temp_config_manager.config_data = new_config
        temp_config_manager._parse_config()
        
        errors = temp_config_manager.validate_config()
        if errors:
            raise ValueError(f"Invalid configuration: {errors}")
        
        # Применение новой конфигурации
        self.config_manager.config_data = new_config
        self.config_manager._parse_config()
        
        # Перезапуск pipeline с новой конфигурацией
        if self.running:
            await self.stop()
            await self.initialize()
            await self.start()
        
        print("Configuration updated successfully")
    
    async def save_config(self, config_path: str):
        """Сохранение конфигурации в файл"""
        self.config_manager.save_config(config_path)
        print(f"Configuration saved to {config_path}")
    
    async def load_config(self, config_path: str):
        """Загрузка конфигурации из файла"""
        self.config_manager.load_config(config_path)
        
        # Перезапуск с новой конфигурацией
        if self.running:
            await self.stop()
            await self.initialize()
            await self.start()
        
        print(f"Configuration loaded from {config_path}")

    # --- Реализация абстрактных методов EvilEyeBase ---
    def default(self):
        pass

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}

    # --- Методы для совместимости с MainWindow ---
    def init_main_window(self, main_window, slots, signals):
        """Инициализация главного окна для совместимости"""
        self.main_window = main_window
        self.pyqt_slots = slots
        self.pyqt_signals = signals
        
        # Инициализация визуализатора после получения slots и signals
        if 'visualizer' in self.params:
            self._init_visualizer(self.params['visualizer'])
        
        print("MainWindow initialized with AsyncController")

    def set_current_main_widget_size(self, width: int, height: int):
        """Установка размера главного виджета"""
        self.current_main_widget_size = [width, height]

    def is_running(self) -> bool:
        """Проверка, работает ли контроллер"""
        return self.running

    def add_channel(self):
        """Добавление канала (заглушка для совместимости)"""
        print("Add channel method called (not implemented in AsyncController)")

    def release(self):
        """Освобождение ресурсов"""
        asyncio.create_task(self.stop())
        if self.pipeline:
            self.pipeline.release()
        print('Everything in AsyncController released')

    def save_params(self, params: dict):
        """Сохранение параметров (для совместимости)"""
        # Обновляем параметры в config_manager
        self.config_manager.config_data = params
        
        # Сохраняем параметры контроллера
        if 'controller' not in params:
            params['controller'] = dict()
        
        params['controller']["autoclose"] = self.autoclose
        params['controller']["fps"] = self.fps
        params['controller']["show_main_gui"] = self.show_main_gui
        params['controller']["show_journal"] = self.show_journal
        params['controller']["enable_close_from_gui"] = self.enable_close_from_gui
        params['controller']["class_names"] = self.class_names
        params['controller']["memory_periodic_check_sec"] = self.memory_periodic_check_sec
        params['controller']["max_memory_usage_mb"] = self.max_memory_usage_mb
        params['controller']["auto_restart"] = self.auto_restart

        # Получаем параметры pipeline
        if self.pipeline:
            pipeline_params = self.pipeline.get_params()
            params['sources'] = pipeline_params.get('sources', [])
            params['preprocessors'] = pipeline_params.get('preprocessors', [])
            params['detectors'] = pipeline_params.get('detectors', [])
            params['trackers'] = pipeline_params.get('trackers', [])
            params['mc_trackers'] = pipeline_params.get('mc_trackers', [])

        # Параметры обработчика объектов
        if self.obj_handler:
            params['objects_handler'] = self.obj_handler.get_params()

        # Параметры детекторов событий
        params['events_detectors'] = dict()
        if self.cam_events_detector:
            params['events_detectors']['CamEventsDetector'] = self.cam_events_detector.get_params()
        if self.fov_events_detector:
            params['events_detectors']['FieldOfViewEventsDetector'] = self.fov_events_detector.get_params()
        if self.zone_events_detector:
            params['events_detectors']['ZoneEventsDetector'] = self.zone_events_detector.get_params()

        # Параметры процессора событий
        if self.events_processor:
            params['events_processor'] = self.events_processor.get_params()
        
        # Параметры визуализатора
        if self.visualizer:
            params['visualizer'] = self.visualizer.get_params()
        else:
            params['visualizer'] = dict()
        
        print("Parameters saved in AsyncController")

    @property
    def show_main_gui(self) -> bool:
        """Показывать ли главное GUI"""
        return self._show_main_gui

    @show_main_gui.setter
    def show_main_gui(self, value: bool):
        self._show_main_gui = value

    @property
    def show_journal(self) -> bool:
        """Показывать ли журнал"""
        return self._show_journal

    @show_journal.setter
    def show_journal(self, value: bool):
        self._show_journal = value

    @property
    def enable_close_from_gui(self) -> bool:
        """Разрешить закрытие из GUI"""
        return self._enable_close_from_gui

    @enable_close_from_gui.setter
    def enable_close_from_gui(self, value: bool):
        self._enable_close_from_gui = value
