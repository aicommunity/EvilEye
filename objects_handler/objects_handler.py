from queue import Queue
from threading import Thread
from threading import Condition

'''
Модуль работы с объектами ожидает данные от детектора в виде dict: {'cam_id': int, 'objects': list, 'actual': bool}, 
элемент objects при этом содержит словари с данными о каждом объекте (рамка, достоверность, класс)

Данные от трекера в виде dict: {'cam_id': int, 'objects': list}, где objects тоже содержит словари с данными о каждом
объекте (айди, рамка, достоверность, класс). Эти данные затем преобразуются к виду массива словарей, где каждый словарь
соответствует конкретному объекту и содержит его историю в виде dict:
{'obj_id': int, 'obj_info': list, 'lost_frames': int, 'last_update': bool}, где obj_info содержит словари,
полученные на входе (айди, рамка, достоверность, класс), которые соответствуют данному объекту.
'''


class ObjectsHandler:
    def __init__(self, cams_num, history_len=1, lost_thresh=5):
        # Очередь для потокобезопасного приема данных от каждой камеры
        self.objs_queue = Queue()
        # Списки для хранения различных типов объектов
        self.new_objs = []
        self.active_objs = []
        self.lost_objs = []
        self.history = history_len
        self.lost_thresh = lost_thresh  # Порог перевода (в кадрах) в потерянные объекты
        self.cams_num = cams_num
        for i in range(self.cams_num):
            self.active_objs.append({'cam_id': i, 'objects': []})
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
            frame_objs = self.objs_queue.get()
            # Блокируем остальные потоки для предотвращения одновременного обращения к объектам
            with self.condition:
                if frame_objs['objects'][0].get('obj_id') is not None:  # Если объекты получены от трекера
                    self._handle_active(frame_objs)
                else:  # Проверяем, есть ли в списке новых объектов предыдущая детекция с этой камеры, если да, заменяем на новую
                    idx = next((i for i, item in enumerate(self.new_objs) if item['cam_id'] == frame_objs['cam_id']), None)
                    if idx is not None:
                        del self.new_objs[idx]
                    self.new_objs.append(frame_objs)
                    # Оповещаем остальные потоки, снимаем блокировку
                self.condition.notify()
            self.objs_queue.task_done()

    def _handle_active(self, frame_objs):
        for cam_active in self.active_objs:  # Проходим по данным со всех камер
            if frame_objs['cam_id'] == cam_active['cam_id']:  # Если объекты были получены с данной камеры
                if len(cam_active['objects']) == 0:  # Если нет отслеживаемых объектов, то просто добавляем все новые
                    for obj in frame_objs['objects']:
                        tracked_obj = {'obj_id': obj['obj_id'], 'obj_info': [obj], 'lost_frames': 0, 'last_update': False}
                        cam_active['objects'].append(tracked_obj)
                else:  # Иначе проверяем все отслеживаемые объекты
                    self._find_in_tracked(cam_active, frame_objs)
                break

    def _move_to_lost(self, obj):
        self.lost_objs.append(obj)

    def _find_in_tracked(self, active_objs, frame_objs):
        for obj in frame_objs['objects']:
            was_appended = False  # Флаг, который показывает, новый ли это объект или его уже отслеживали
            for cam_obj in active_objs['objects']:
                # Если объект с таким айди найден в отслеживаемых, то добавляем новые координаты рамки к его истории
                if obj['obj_id'] == cam_obj['obj_id']:
                    cam_obj['obj_info'].append(obj)
                    cam_obj['last_update'] = True  # Был ли данный объект обновлен на этом кадре
                    was_appended = True
                    cam_obj['lost_frames'] = 0  # Кол-во последовательных кадров, на которых объекта не было
                    if len(cam_obj['obj_info']) > self.history:  # Если количество данных превышает размер истории, удаляем самые старые данные об объекте
                        del cam_obj['obj_info'][0]
                    break
            if not was_appended:  # Если это новый объект, то создаем новый словарь для него
                tracked_obj = {'obj_id': obj['obj_id'], 'obj_info': [obj], 'lost_frames': 0, 'last_update': True}
                active_objs['objects'].append(tracked_obj)
        del_idxs = []
        for i, cam_obj in enumerate(active_objs['objects']):  # Цикл для перевода объектов в потерянные
            if not cam_obj['last_update']:  # Если на последнем кадре не было обновления, то увеличиваем счетчик
                cam_obj['lost_frames'] += 1
                if cam_obj['lost_frames'] >= self.lost_thresh:
                    del_idxs.append(i)
                    self._move_to_lost(cam_obj)  # Отправляем в потерянные, если отсутствует больше порога кадров
            else:
                cam_obj['last_update'] = False  # Сбрасываем флаги
        for idx in reversed(del_idxs):  # Удаление потерянных объектов из активных
            del active_objs['objects'][idx]
