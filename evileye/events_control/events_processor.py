import time
from queue import Queue
from threading import Thread
from ..core.base_class import EvilEyeBase
from psycopg2 import sql
import datetime


class EventsProcessor(EvilEyeBase):
    def __init__(self, db_adapters: list, db_controller):
        super().__init__()
        self.id_counter = 0

        self.queue = Queue()
        self.processing_thread = Thread(target=self.process)
        self.run_flag = False
        self.db_adapters = db_adapters
        self.db_controller = db_controller
        self.events_adapters = {}  # Сопоставляет имена событий с соответствующими им адаптерами
        self.events_tables = {}  # Сопоставляет имена событий с именами таблиц БД
        self.lost_store_time_secs = 10

        self.long_term_events = {}
        self.finished_events = {}
        self.ui_callback = None  # callback: (source_id, event_name, is_on, bbox_norm)

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return dict()

    def init_impl(self):
        self.events_adapters = {adapter.get_event_name(): adapter for adapter in self.db_adapters}
        self.events_tables = {adapter.get_event_name(): adapter.get_table_name() for adapter in self.db_adapters}
        try:
            self.logger.info(f"EventsProcessor initialized with adapters: {list(self.events_adapters.keys())}")
        except Exception:
            pass

    def set_ui_callback(self, cb):
        self.ui_callback = cb

    def get_last_id(self):  # Функция для получения последнего id события из БД
        # Return 0 if no database controller is available
        if self.db_controller is None:
            return 0
            
        table_names = list(self.events_tables.values())
        if not table_names:  # No tables available
            return 0
            
        subqueries = []
        # Объединяем результаты из всех таблиц событий, выбираем максимальный id
        for i in range(len(table_names) - 1):
            subquery = sql.SQL('SELECT MAX(event_id) as event_id FROM {table} UNION').format(
                table=sql.Identifier(table_names[i]))
            subqueries.append(subquery)
        subquery = sql.SQL('SELECT MAX(event_id) as event_id FROM {table}').format(
            table=sql.Identifier(table_names[-1]))
        subqueries.append(subquery)

        query = sql.SQL('SELECT MAX(event_id) FROM ({subqueries}) AS temp').format(
            subqueries=sql.SQL(' ').join(subqueries))
        record = self.db_controller.query(query)

        # Check if record is None or empty
        if record is None or len(record) == 0 or len(record[0]) == 0 or record[0][0] is None:
            return 0
        return record[0][0] + 1

    def default(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    def put(self, events):
        self.queue.put(events)

    def start(self):
        self.id_counter = self.get_last_id()
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        # Gracefully flush pending events before stopping
        try:
            # Wait up to ~0.5s for queue to drain
            max_wait_secs = 0.5
            waited = 0.0
            while not self.queue.empty() and waited < max_wait_secs:
                time.sleep(0.01)
                waited += 0.01
        except Exception:
            pass

        # Signal processing thread to exit
        self.run_flag = False
        try:
            self.queue.put(None)
        except Exception:
            pass

        # Join processing thread
        if self.processing_thread.is_alive():
            try:
                self.processing_thread.join(timeout=0.5)
            except Exception:
                pass

    def process(self):
        filtered_long_term = {key: None for key in self.long_term_events}
        while self.run_flag:
            #time.sleep(0.01)
            new_events = self.queue.get()
            if new_events is None:
                continue
            # print(new_events)

            finished_idxs = set()
            for events in new_events:
                long_term = self.long_term_events.get(events,
                                                      None)  # Получаем список долгосрочных событий, которые сейчас активны
                if long_term:
                    for event in new_events[events]:  # Проходим по всем событиям одного типа
                        for i in range(len(long_term)):
                            if event == long_term[i]:  # Проверяем, есть ли это событие в долгосрочных
                                if event.is_finished():  # Обновляем запись о долгосрочном событии, если оно закончилось
                                    long_term[i].update_on_finished(
                                        event)  # Обновляем информацию о событии по его завершении
                                if event.get_name() in self.events_adapters:
                                        self.events_adapters[event.get_name()].update(long_term[i])  # Получаем адаптер по имени события, отправляем в него завершенное
                                # Notify UI: event OFF (независимо от наличия адаптера)
                                try:
                                    if self.ui_callback:
                                        # Emit OFF with (source_id, object_id, event_name)
                                        self.ui_callback(event.source_id,
                                                         getattr(event, 'object_id', -1),
                                                         getattr(event, 'matched_event_name', ''),
                                                         False)
                                except Exception:
                                    pass
                                    if events not in self.finished_events:
                                        self.finished_events[events] = []
                                    self.finished_events[events].append(event)
                                    finished_idxs.add(i)
                                break
                        else:  # no break. Если событие новое, добавляем его в долгосрочные
                            event.set_id(self.id_counter)
                            self.id_counter += 1
                            self.long_term_events[events].append(event)
                            if event.get_name() in self.events_adapters:
                                self.events_adapters[event.get_name()].insert(event)
                            # UI: ON для нового долгосрочного события в уже активной группе
                            try:
                                if self.ui_callback and not event.is_finished():
                                    self.ui_callback(event.source_id,
                                                     getattr(event, 'object_id', -1),
                                                     getattr(event, 'matched_event_name', ''),
                                                     True)
                            except Exception:
                                pass
                else:  # Если нет активных долгосрочных событий, анализируем новые
                    for event in new_events[events]:
                        event.set_id(self.id_counter)
                        self.id_counter += 1
                        if event.is_long_term():  # Если событие долгосрочное и не завершено, делаем его активным
                            if events not in self.long_term_events:
                                self.long_term_events[events] = []
                            if event.is_finished():  # Если новое долгосрочное событие уже пришло завершенным (на случай поиска в истории)
                                if events not in self.finished_events:
                                    self.finished_events[events] = []
                                self.finished_events[events].append(event)
                                if event.get_name() in self.events_adapters:
                                    self.events_adapters[event.get_name()].insert(event)
                                # Для long_term события, пришедшего уже завершённым, не шлём ON, только OFF
                                try:
                                    if self.ui_callback:
                                        self.ui_callback(event.source_id, getattr(event, 'object_id', -1), getattr(event, 'matched_event_name', ''), False)
                                except Exception:
                                    pass
                            else:
                                self.long_term_events[events].append(event)
                                # Notify UI: event ON
                                try:
                                    if self.ui_callback:
                                        self.ui_callback(event.source_id,
                                                         getattr(event, 'object_id', -1),
                                                         getattr(event, 'matched_event_name', ''),
                                                         True,
                                                         getattr(event, 'box_found', None))
                                except Exception:
                                    pass
                        else:  # Иначе отправляем в завершенные (краткосрочные события)
                            if events not in self.finished_events:
                                self.finished_events[events] = []
                            self.finished_events[events].append(event)
                            if event.get_name() in self.events_adapters:
                                self.events_adapters[event.get_name()].insert(event)
                            # Notify UI for non-long events: ON then OFF
                            try:
                                if self.ui_callback and not event.is_long_term():
                                    self.ui_callback(event.source_id,
                                                     getattr(event, 'object_id', -1),
                                                     getattr(event, 'matched_event_name', ''),
                                                     True,
                                                     getattr(event, 'box_found', None))
                                    self.ui_callback(event.source_id,
                                                     getattr(event, 'object_id', -1),
                                                     getattr(event, 'matched_event_name', ''),
                                                     False,
                                                     None)
                            except Exception:
                                pass
                # Удаляем завершенные долгосрочные события
                if events in self.long_term_events:
                    filtered_long_term[events] = [self.long_term_events[events][i] for i in range(len(self.long_term_events[events])) if i not in finished_idxs]
                    self.long_term_events[events] = filtered_long_term[events]

            for events in self.finished_events:
                start_index_for_remove = None
                for i in reversed(range(len(self.finished_events[events]))):
                    if (datetime.datetime.now() - self.finished_events[events][i].get_time_finished()).total_seconds() > self.lost_store_time_secs:
                        start_index_for_remove = i
                        break
                if start_index_for_remove is not None:
                    if start_index_for_remove == 0:
                        self.finished_events[events] = []
                    else:
                        self.finished_events[events] = self.finished_events[events][start_index_for_remove:]
                # print(self.finished_events[events])
