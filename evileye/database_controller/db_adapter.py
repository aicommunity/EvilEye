from ..core.base_class import EvilEyeBase
from .database_controller_pg import DatabaseControllerPg
from threading import Thread
from queue import Queue
from abc import abstractmethod, ABC


class DatabaseAdapterBase(EvilEyeBase, ABC):
    def __init__(self, db_controller):
        super().__init__()
        self.db_controller = db_controller
        self.db_params = self.db_controller.get_params()
        self.cameras_params = self.db_controller.get_cameras_params()
        self.query_thread = Thread(target=self._execute_query)
        self.run_flag = False
        self.queue_in = Queue()
        self.table_name = None
        self.event_name = None

    def set_params_impl(self):
        self.table_name = self.params['table_name']

    def get_params_impl(self):
        params = dict()
        params['table_name'] = self.table_name
        return params

    def init_impl(self):
        pass

    def get_event_name(self):
        return self.event_name

    def get_table_name(self):
        return self.table_name

    def start(self):
        self.run_flag = True
        self.query_thread.start()

    def stop(self):
        self.run_flag = False
        if self.query_thread.is_alive():
            self.query_thread.join()

    def default(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    def insert(self, data):
        self._insert_impl(data)

    def update(self, data):
        self._update_impl(data)

    def get_db_params(self):
        return self.db_params

    def get_cameras_params(self):
        return self.cameras_params

    @abstractmethod
    def _execute_query(self):
        pass

    @abstractmethod
    def _insert_impl(self, data):
        pass

    @abstractmethod
    def _update_impl(self, data):
        pass


