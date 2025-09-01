from abc import ABC, abstractmethod
from ..core.base_class import EvilEyeBase
import threading
from queue import Queue


class DatabaseControllerBase(EvilEyeBase):
    def __init__(self, controller_type):
        super().__init__()
        self.host_name = "localhost"
        self.database_name = ""
        self.user_name = ""
        self.password = ""
        self.controller_type = controller_type
        print(controller_type)
        self.run_flag = False
        if self.controller_type == 'Writer':
            self.query_thread = threading.Thread(target=self._insert_impl)
        else:
            self.query_thread = None
        self.queue_in = Queue()
        self.queue_out = Queue()

    def connect(self):
        if self.get_init_flag():
            return self.connect_impl()
        else:
            raise Exception('init function has not been called')

    def disconnect(self):
        if self.get_init_flag():
            return self.disconnect_impl()
        else:
            raise Exception('init function has not been called')

    def get(self):
        if self.queue_out.empty():
            return None
        else:
            return self.queue_out.get()

    def query(self, query_string, data=None):
        if self.get_init_flag():
            return self.query_impl(query_string, data)
        else:
            raise Exception('init function has not been called')

    def start(self):
        if self.query_thread:
            print('Started writer db')
            self.run_flag = True
            self.query_thread.start()

    def stop(self):
        if self.query_thread:
            self.run_flag = False
            self.queue_in.put((None,))
            if self.query_thread.is_alive():
                self.query_thread.join()
        print('DataBase stopped')

    @abstractmethod
    def connect_impl(self):
        pass

    @abstractmethod
    def disconnect_impl(self):
        pass

    @abstractmethod
    def query_impl(self, query_string, data=None):
        pass

    @abstractmethod
    def _insert_impl(self):
        pass
