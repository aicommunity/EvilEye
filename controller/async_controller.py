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
        
        # Регистрация сервисов
        self._register_services()
    
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
            # Валидация конфигурации
            config_errors = self.config_manager.validate_config()
            if config_errors:
                raise ValueError(f"Configuration errors: {config_errors}")
            
            # Создание и настройка pipeline
            await self._setup_pipeline(pipeline_config)
            
            # Регистрация pipeline в сервисном контейнере
            if self.pipeline:
                self.service_container.register('pipeline', self.pipeline)
            
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
            # Здесь должна быть логика создания конкретных процессоров
            # Пока возвращаем заглушку
            print(f"Creating processor: {name} of type {processor_type}")
            
            # Создание заглушки процессора
            class DummyProcessor(AsyncProcessorBase):
                async def process_data(self, data):
                    return data
            
            processor = DummyProcessor(
                max_queue_size=config.get('max_queue_size', 10),
                timeout=config.get('timeout', 0.1)
            )
            
            return processor
            
        except Exception as e:
            print(f"Error creating processor {name}: {e}")
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
