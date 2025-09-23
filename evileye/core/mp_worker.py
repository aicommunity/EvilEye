from abc import ABC, abstractmethod
import multiprocessing as mp
from .logger import get_module_logger

# Глобальные константы
#MODEL_PATH = 'yolov8n.pt'
#NUM_PROCESSES = 4  # Количество процессов
#QUEUE_TIMEOUT = 2  # Таймаут чтения очереди (сек)
#MAX_QUEUE_SIZE = 10  # Макс. размер очереди (предотвращает переполнение)

class MpWorker(ABC):
    def __init__(self, input_queue, output_queue):
        self.logger = get_module_logger("mp_worker")
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.queue_timeout = 2

    @abstractmethod
    def init_worker(self):
        pass

    @abstractmethod
    def worker_impl(self, data):
        pass

    def __call__(self):
        self.init_worker()
        self.logger.info(f"Process {mp.current_process().name} ready")

        while True:
            try:
                data = self.input_queue.get(timeout=self.queue_timeout)
                if data is None:
                    break
                results = self.worker_impl(data)
                self.output_queue.put(results)
            except mp.queues.Empty:
                self.logger.info(f"Process {mp.current_process().name} ends by timeout")
                break
            except Exception as e:
                self.logger.info(f"Error in process {mp.current_process().name}: {str(e)}")
                break

