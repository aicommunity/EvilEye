from abc import ABC, abstractmethod
import core


class DatabaseControllerBase(core.EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.host_name = "localhost"
        self.database_name = ""
        self.user_name = ""
        self.password = ""

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

    def query(self, query_string, data=None):
        if self.get_init_flag():
            return self.query_impl(query_string, data)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def connect_impl(self):
        pass

    @abstractmethod
    def disconnect_impl(self):
        pass

    @abstractmethod
    def query_impl(self, query_string, data=None):
        pass

