import psycopg2

import database_controller
import psycopg2 as pg
from psycopg2 import sql
from psycopg2 import pool
import copy


# see https://ru.hexlet.io/blog/posts/python-postgresql


class DatabaseControllerPg(database_controller.DatabaseControllerBase):
    def __init__(self):
        super().__init__()
        self.conn_pool = None
        self.user_name = ""
        self.password = ""
        self.database_name = ""
        self.host_name = ""
        self.port = 0
        self.tables = None

    def set_params_impl(self):
        self.user_name = self.params['user_name']
        self.password = self.params['password']
        self.database_name = self.params['database_name']
        self.host_name = self.params['host_name']
        self.port = self.params['port']
        self.tables = copy.deepcopy(self.params['tables'])

    def default(self):
        self.params['user_name'] = "postgres"
        self.params['password'] = ""
        self.params['database_name'] = "evil_eye_db"
        self.params['host_name'] = "localhost"
        self.params['port'] = 5432
        self.set_params_impl()

    def init_impl(self):
        return True

    def reset_impl(self):
        pass

    def connect_impl(self):
        self.conn_pool = pool.ThreadedConnectionPool(1, 10, user=self.user_name,
                                                     password=self.password, host=self.host_name,
                                                     port=self.port, database=self.database_name)
        for table_name in self.tables.keys():
            self.create_table(table_name)
        # self.connection = pg.connect(dbname=self.database_name, user=self.user_name, password=self.password, host=self.host_name, port=self.port)

    def disconnect_impl(self):
        self.conn_pool.closeall()

    def query_impl(self, query_string, data=None):
        connection = None
        try:
            connection = self.conn_pool.getconn()
            with connection:
                with connection.cursor() as curs:
                    print(query_string.as_string(curs))
                    curs.execute(query_string, data)
        except psycopg2.OperationalError:
            print(f'Transaction ({query_string}) is not committed')
        finally:
            if connection:
                self.conn_pool.putconn(connection)

    def get_fields_names(self, table_name):
        return self.tables[table_name].keys()

    def create_table(self, table_name):
        self.query(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_name)))

        fields = []
        for key, value in self.tables[table_name].items():
            fields.append(sql.SQL("{} {}").format(sql.Identifier(key), sql.SQL(value)))

        create_table = sql.SQL("CREATE TABLE {table}({fields})").format(
            table=sql.Identifier(table_name),
            fields=sql.SQL(',').join(fields))
        self.query(create_table)

    def put(self, table_name, data):
        fields = self.tables[table_name].keys()
        insert_query = sql.SQL("INSERT INTO {} VALUES ({})").format(
            sql.Identifier(table_name),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.query(insert_query, data)

    def get_obj_info(self, table_name, obj_id):
        connection = None
        try:
            result = {}
            connection = self.conn_pool.getconn()
            with connection:
                with connection.cursor() as curs:
                    query = sql.SQL("SELECT * from {} WHERE id = %s").format(sql.Identifier(table_name))
                    curs.execute(query, (obj_id,))
                    result[table_name] = curs.fetchall()
            return result
        except psycopg2.OperationalError:
            print(f'Transaction (get obj with id={obj_id}) is not committed')
            return {}
        finally:
            if connection:
                self.conn_pool.putconn(connection)

    def delete_obj(self, table_name, obj_id):
        del_query = sql.SQL("DELETE from {} WHERE id = %s").format(sql.Identifier(table_name))
        self.query(del_query, (obj_id,))

    def release_impl(self):
        pass


if __name__ == '__main__':
    import json

    params_file = open('D:/Git/EvilEye/samples/visual_sample.json')
    parameters = json.load(params_file)
    db = DatabaseControllerPg()
    db.set_params(**parameters['database'])
    db.init()
    db.connect()
    db.create_table('emerged')
    db.create_table('lost')
    db.put('emerged', (1, [45.0, 37.0, 94.0, 273.0], 77.5, 1.0))
    db.put('emerged', (2, [55.0, 47.0, 94.0, 273.0], 70.5, 1.0))
    db.put('lost', (1, [50.0, 20.0, 33.0, 144.0], 76.0, 1.0))
    res = db.get_obj_info('emerged', obj_id=1)
    print(res)
    db.disconnect()
