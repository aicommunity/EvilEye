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

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return dict()

    def init_impl(self):
        self.events_adapters = {adapter.get_event_name(): adapter for adapter in self.db_adapters}
        self.events_tables = {adapter.get_event_name(): adapter.get_table_name() for adapter in self.db_adapters}
        # print(self.events_adapters)

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
        self.run_flag = False
        self.queue.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()

    def process(self):
        filtered_long_term = {key: None for key in self.long_term_events}
        while self.run_flag:
            time.sleep(0.01)
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
                            else:
                                self.long_term_events[events].append(event)
                        else:  # Иначе отправляем в завершенные
                            if events not in self.finished_events:
                                self.finished_events[events] = []
                            self.finished_events[events].append(event)
                        if event.get_name() in self.events_adapters:
                            self.events_adapters[event.get_name()].insert(event)
                # Удаляем завершенные долгосрочные события
                if events in self.long_term_events:
                    filtered_long_term[events] = [self.long_term_events[events][i] for i
                                                  in range(len(self.long_term_events[events])) if i not in finished_idxs]
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
