import asyncio
from typing import Dict, List, Any, Optional, Tuple
from collections import deque
import time
from datetime import datetime

from core.async_components import AsyncPipeline, AsyncProcessorBase
from core.async_components.data_types import Frame, DetectionResult, TrackingResult, BoundingBox, Track
from core.async_components.config_manager import PipelineConfig
from .model_pool import ModelPool


class AsyncPipelineSurveillance(AsyncPipeline):
    """
    Оптимизированный асинхронный pipeline для видеонаблюдения.
    Обеспечивает параллельную обработку: capture → detection → tracking → multi-camera tracking
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        super().__init__(config)
        
        # Специализированные процессоры
        self.capture_processor: Optional[AsyncProcessorBase] = None
        self.preprocessing_processor: Optional[AsyncProcessorBase] = None
        self.detection_processor: Optional[AsyncProcessorBase] = None
        self.tracking_processor: Optional[AsyncProcessorBase] = None
        self.mc_tracking_processor: Optional[AsyncProcessorBase] = None
        
        # Пул моделей для оптимизации
        self.detection_model_pool: Optional[ModelPool] = None
        self.tracking_model_pool: Optional[ModelPool] = None
        
        # Буферы для батчевой обработки
        self.frame_buffer = deque(maxlen=30)
        self.detection_buffer = deque(maxlen=10)
        self.tracking_buffer = deque(maxlen=10)
        
        # Статистика по этапам
        self.stage_metrics = {
            'capture_time': 0.0,
            'preprocessing_time': 0.0,
            'detection_time': 0.0,
            'tracking_time': 0.0,
            'mc_tracking_time': 0.0
        }
    
    def setup_processors(self, 
                        capture_processor: AsyncProcessorBase,
                        detection_processor: AsyncProcessorBase,
                        tracking_processor: AsyncProcessorBase,
                        preprocessing_processor: Optional[AsyncProcessorBase] = None,
                        mc_tracking_processor: Optional[AsyncProcessorBase] = None):
        """Настройка процессоров pipeline"""
        self.capture_processor = capture_processor
        self.preprocessing_processor = preprocessing_processor
        self.detection_processor = detection_processor
        self.tracking_processor = tracking_processor
        self.mc_tracking_processor = mc_tracking_processor
        
        # Добавление в общий словарь процессоров
        self.add_processor('capture', capture_processor)
        if preprocessing_processor:
            self.add_processor('preprocessing', preprocessing_processor)
        self.add_processor('detection', detection_processor)
        self.add_processor('tracking', tracking_processor)
        if mc_tracking_processor:
            self.add_processor('mc_tracking', mc_tracking_processor)
    
    def setup_model_pools(self, 
                         detection_model_class=None,
                         tracking_model_class=None,
                         detection_pool_size: int = 2,
                         tracking_pool_size: int = 2):
        """Настройка пулов моделей"""
        if detection_model_class:
            self.detection_model_pool = ModelPool(
                detection_model_class, 
                pool_size=detection_pool_size
            )
        
        if tracking_model_class:
            self.tracking_model_pool = ModelPool(
                tracking_model_class, 
                pool_size=tracking_pool_size
            )
    
    async def _process_frame_through_pipeline(self, frame: Frame) -> Optional[TrackingResult]:
        """
        Обработка кадра через весь pipeline с параллельной обработкой этапов
        """
        start_time = time.time()
        
        try:
            # Этап 1: Capture (если нужно)
            capture_start = time.time()
            if self.capture_processor:
                # Здесь может быть логика получения кадра из источника
                pass
            self.stage_metrics['capture_time'] = time.time() - capture_start
            
            # Этап 2: Preprocessing
            preprocessing_start = time.time()
            preprocessed_frame = frame
            if self.preprocessing_processor:
                preprocessed_frame = await self._process_preprocessing(frame)
            self.stage_metrics['preprocessing_time'] = time.time() - preprocessing_start
            
            # Этап 3: Detection
            detection_start = time.time()
            detection_result = await self._process_detection(preprocessed_frame)
            self.stage_metrics['detection_time'] = time.time() - detection_start
            
            if not detection_result:
                return None
            
            # Этап 4: Tracking
            tracking_start = time.time()
            tracking_result = await self._process_tracking(detection_result)
            self.stage_metrics['tracking_time'] = time.time() - tracking_start
            
            if not tracking_result:
                return None
            
            # Этап 5: Multi-camera tracking
            mc_tracking_start = time.time()
            if self.mc_tracking_processor:
                final_result = await self._process_mc_tracking(tracking_result)
            else:
                final_result = tracking_result
            self.stage_metrics['mc_tracking_time'] = time.time() - mc_tracking_start
            
            return final_result
            
        except Exception as e:
            print(f"Error in pipeline processing: {e}")
            return None
    
    async def _process_preprocessing(self, frame: Frame) -> Frame:
        """Обработка препроцессинга"""
        if not self.preprocessing_processor:
            return frame
        
        try:
            # Отправка кадра в процессор препроцессинга
            await self.preprocessing_processor.put(frame)
            
            # Получение результата
            result = await self.preprocessing_processor.get()
            if result:
                return result
            else:
                return frame
        except Exception as e:
            print(f"Error in preprocessing: {e}")
            return frame
    
    async def _process_detection(self, frame: Frame) -> Optional[DetectionResult]:
        """Обработка детекции с использованием пула моделей"""
        if not self.detection_processor:
            return None
        
        try:
            # Получение модели из пула если доступен
            model = None
            if self.detection_model_pool:
                model = await self.detection_model_pool.get_model()
            
            try:
                # Отправка кадра в процессор детекции
                await self.detection_processor.put(frame)
                
                # Получение результата
                result = await self.detection_processor.get()
                return result
            finally:
                # Возврат модели в пул
                if model and self.detection_model_pool:
                    await self.detection_model_pool.return_model(model)
                    
        except Exception as e:
            print(f"Error in detection: {e}")
            return None
    
    async def _process_tracking(self, detection_result: DetectionResult) -> Optional[TrackingResult]:
        """Обработка трекинга с использованием пула моделей"""
        if not self.tracking_processor:
            return None
        
        try:
            # Получение модели из пула если доступен
            model = None
            if self.tracking_model_pool:
                model = await self.tracking_model_pool.get_model()
            
            try:
                # Отправка результата детекции в процессор трекинга
                await self.tracking_processor.put(detection_result)
                
                # Получение результата
                result = await self.tracking_processor.get()
                return result
            finally:
                # Возврат модели в пул
                if model and self.tracking_model_pool:
                    await self.tracking_model_pool.return_model(model)
                    
        except Exception as e:
            print(f"Error in tracking: {e}")
            return None
    
    async def _process_mc_tracking(self, tracking_result: TrackingResult) -> TrackingResult:
        """Обработка мультикамерного трекинга"""
        if not self.mc_tracking_processor:
            return tracking_result
        
        try:
            # Отправка результата трекинга в процессор мультикамерного трекинга
            await self.mc_tracking_processor.put(tracking_result)
            
            # Получение результата
            result = await self.mc_tracking_processor.get()
            if result:
                return result
            else:
                return tracking_result
        except Exception as e:
            print(f"Error in multi-camera tracking: {e}")
            return tracking_result
    
    async def process_batch_optimized(self, frames: List[Frame]) -> List[TrackingResult]:
        """
        Оптимизированная батчевая обработка с параллельной обработкой этапов
        """
        if not self.running:
            return []
        
        # Разделение кадров на батчи для каждого этапа
        batch_size = min(len(frames), 5)  # Максимальный размер батча
        
        results = []
        for i in range(0, len(frames), batch_size):
            batch = frames[i:i + batch_size]
            
            # Параллельная обработка батча
            batch_results = await self._process_batch_parallel(batch)
            results.extend(batch_results)
        
        return results
    
    async def _process_batch_parallel(self, frames: List[Frame]) -> List[TrackingResult]:
        """Параллельная обработка батча кадров"""
        # Создание задач для параллельной обработки
        tasks = []
        for frame in frames:
            task = asyncio.create_task(self.process_frame(frame))
            tasks.append(task)
        
        # Ожидание завершения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтрация результатов
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error in batch processing: {result}")
                self.performance_metrics['errors_count'] += 1
            elif result is not None:
                valid_results.append(result)
        
        return valid_results
    
    async def start(self):
        """Запуск pipeline с пулами моделей"""
        await super().start()
        
        # Запуск пулов моделей
        if self.detection_model_pool:
            await self.detection_model_pool.start()
        
        if self.tracking_model_pool:
            await self.tracking_model_pool.start()
        
        print(f"AsyncPipelineSurveillance {self.config.name} started")
    
    async def stop(self):
        """Остановка pipeline с пулами моделей"""
        # Остановка пулов моделей
        if self.detection_model_pool:
            await self.detection_model_pool.stop()
        
        if self.tracking_model_pool:
            await self.tracking_model_pool.stop()
        
        await super().stop()
        print(f"AsyncPipelineSurveillance {self.config.name} stopped")
    
    def get_detailed_metrics(self) -> Dict[str, Any]:
        """Получение детальных метрик pipeline"""
        base_metrics = self.get_metrics()
        
        # Добавление метрик этапов
        detailed_metrics = {
            **base_metrics,
            'stage_metrics': self.stage_metrics,
            'model_pools': {}
        }
        
        # Метрики пулов моделей
        if self.detection_model_pool:
            detailed_metrics['model_pools']['detection'] = self.detection_model_pool.get_stats()
        
        if self.tracking_model_pool:
            detailed_metrics['model_pools']['tracking'] = self.tracking_model_pool.get_stats()
        
        return detailed_metrics
    
    async def health_check(self) -> Dict[str, Any]:
        """Расширенная проверка состояния"""
        base_health = await super().health_check()
        
        # Добавление информации о пулах моделей
        model_pools_health = {}
        if self.detection_model_pool:
            model_pools_health['detection'] = self.detection_model_pool.get_stats()
        
        if self.tracking_model_pool:
            model_pools_health['tracking'] = self.tracking_model_pool.get_stats()
        
        base_health['model_pools_health'] = model_pools_health
        
        # Определение общего состояния
        if any(pool.get('cache_hit_rate', 0) < 0.5 for pool in model_pools_health.values()):
            base_health['overall_health'] = 'degraded'
        
        return base_health
    
    def get_performance_recommendations(self) -> List[str]:
        """Получение рекомендаций по оптимизации производительности"""
        recommendations = []
        
        # Анализ метрик этапов
        total_time = sum(self.stage_metrics.values())
        if total_time > 0:
            detection_ratio = self.stage_metrics['detection_time'] / total_time
            if detection_ratio > 0.7:
                recommendations.append("Detection is bottleneck. Consider: 1) Increase detection model pool size 2) Use lighter model 3) Reduce input resolution")
            
            tracking_ratio = self.stage_metrics['tracking_time'] / total_time
            if tracking_ratio > 0.3:
                recommendations.append("Tracking is slow. Consider: 1) Increase tracking model pool size 2) Optimize tracking algorithm")
        
        # Анализ пулов моделей
        if self.detection_model_pool:
            detection_stats = self.detection_model_pool.get_stats()
            if detection_stats.get('cache_hit_rate', 0) < 0.5:
                recommendations.append("Low detection model cache hit rate. Consider increasing pool size")
        
        if self.tracking_model_pool:
            tracking_stats = self.tracking_model_pool.get_stats()
            if tracking_stats.get('cache_hit_rate', 0) < 0.5:
                recommendations.append("Low tracking model cache hit rate. Consider increasing pool size")
        
        # Анализ ошибок
        if self.performance_metrics['errors_count'] > 0:
            error_rate = self.performance_metrics['errors_count'] / max(self.performance_metrics['total_frames_processed'], 1)
            if error_rate > 0.1:
                recommendations.append("High error rate. Check system resources and model stability")
        
        return recommendations
