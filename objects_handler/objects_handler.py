from queue import Queue
from threading import Thread
from threading import Condition


class ObjectsHandler:
    def __init__(self):
        # Очередь для потокобезопасного приема данных от каждой камеры
        self.objs_queue = Queue()
        # Списки для хранения различных типов объектов
        self.new_objs = []
        self.active_objs = []
        self.lost_objs = []
        # Условие для блокировки других потоков
        self.condition = Condition()
        # Поток, который отвечает за получение объектов из очереди и распределение их по спискам
        self.handler = Thread(target=self.handle_objs, daemon=True)
        self.handler.start()

    def append(self, objs):  # Добавление детекций с камеры в очередь
        self.objs_queue.put(objs)

    def get(self, objs_type):  # Получение списка объектов в зависимости от указанного типа
        # Блокируем остальные потоки на время получения объектов
        with self.condition:
            self.condition.wait()
            if objs_type == 'new':
                return self.new_objs
            elif objs_type == 'active':
                return self.active_objs
            elif objs_type == 'lost':
                return self.lost_objs
            else:
                raise Exception('Such type of objects does not exist')

    def handle_objs(self):  # Функция, отвечающая за работу с объектами (в данный момент полученными только от детектора)
        print('Handler running: waiting for objects...')
        while True:
            objs = self.objs_queue.get()
            # Блокируем остальные потоки для предотвращения одновременного обращения к объектам
            with self.condition:
                # Проверяем, есть ли в списке новых объектов предыдущая детекция с этой камеры, если да, заменяем на новую
                idx = next((i for i, item in enumerate(self.new_objs) if item['cam_id'] == objs['cam_id']), None)
                if idx is not None:
                    del self.new_objs[idx]
                self.new_objs.append(objs)
                # Оповещаем остальные потоки, снимаем блокировку
                self.condition.notify()
            self.objs_queue.task_done()
