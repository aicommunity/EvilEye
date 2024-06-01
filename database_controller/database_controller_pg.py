import database_controller
import psycopg2 as pg

# see https://ru.hexlet.io/blog/posts/python-postgresql

class DatabaseControllerPg(database_controller.DatabaseControllerBase):
    def __init__(self):
        super().__init__()
        self.connection = None
        self.user_name = ""
        self.password = ""
        self.database_name = ""
        self.host_name = ""
        self.port = 0

    def set_params_impl(self):
        self.user_name = self.params['user_name']
        self.password = self.params['password']
        self.database_name = self.params['database_name']
        self.host_name = self.params['host_name']
        self.port = self.params['port']

    def default(self):
        self.params['user_name'] = "postgres"
        self.params['password'] = ""
        self.params['database_name'] = "evil_eye_db"
        self.params['host_name'] = "localhost"
        self.params['port'] = 5433
        self.set_params_impl()

    def init_impl(self):
        return True

    def reset_impl(self):
        pass
    def connect_impl(self):
        self.connection = pg.connect(dbname=self.database_name, user=self.user_name, password=self.password, host=self.host_name, port=self.port)

    def disconnect_impl(self):
        self.connection.close()

    def query_impl(self, query_string):
        with self.connection.cursor as curs:
            curs.execute(query_string)
            result = curs.fetchall()
            return result

