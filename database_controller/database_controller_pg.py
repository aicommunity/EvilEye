import time
import cv2
from utils import utils
import psycopg2
import pathlib
import os
import utils.utils
import database_controller
from psycopg2 import sql
from psycopg2 import pool
import copy
from utils import event

# see https://ru.hexlet.io/blog/posts/python-postgresql


class DatabaseControllerPg(database_controller.DatabaseControllerBase):
    def __init__(self, controller_type='Writer'):
        super().__init__(controller_type)
        self.conn_pool = None
        self.user_name = ""
        self.password = ""
        self.database_name = ""
        self.host_name = ""
        self.port = 0
        self.image_dir = None
        self.tables = None

    def set_params_impl(self):
        self.user_name = self.params['user_name']
        self.password = self.params['password']
        self.database_name = self.params['database_name']
        self.host_name = self.params['host_name']
        self.port = self.params['port']
        self.image_dir = self.params['image_dir']
        self.tables = copy.deepcopy(self.params['tables'])

    def default(self):
        self.params['user_name'] = "postgres"
        self.params['password'] = ""
        self.params['database_name'] = "evil_eye_db"
        self.params['host_name'] = "localhost"
        self.params['port'] = 5432
        self.params['image_dir'] = utils.get_project_root()
        self.set_params_impl()

    def init_impl(self):
        self.start()
        return True

    def reset_impl(self):
        pass

    def connect_impl(self):
        try:
            self.conn_pool = pool.ThreadedConnectionPool(1, 10, user=self.user_name,
                                                         password=self.password, host=self.host_name,
                                                         port=self.port, database=self.database_name)
        except Exception as ex:
            print(f"Can't connect to database: {ex}")
            self.conn_pool = None

        for table_name in self.tables.keys():
            self.create_table(table_name)

        # self.connection = pg.connect(dbname=self.database_name, user=self.user_name, password=self.password, host=self.host_name, port=self.port)

    def disconnect_impl(self):
        self.stop()
        if self.conn_pool:
            self.conn_pool.closeall()

    def query_impl(self, query_string, data=None):
        if self.conn_pool is None:
            return None

        connection = None
        try:
            connection = self.conn_pool.getconn()
            with connection:
                with connection.cursor() as curs:
                    #print(query_string.as_string(curs))
                    curs.execute(query_string, data)
                    try:
                        result = curs.fetchall()
                    except psycopg2.ProgrammingError:
                        result = None
            return result
        except psycopg2.OperationalError:
            print(f'Transaction ({query_string}) is not committed')
        finally:
            if connection:
                self.conn_pool.putconn(connection)

    def _insert_impl(self):
        while self.run_flag:
            time.sleep(0.01)
            # print(self.queue_in.empty())
            if self.conn_pool is None:
                continue

            try:
                if not self.queue_in.empty():
                    query_string, data, preview_path, frame_path, image = self.queue_in.get()
                    if query_string is not None:
                        pass
                        #print('GOT QUERY')
                    #print(data)
                else:
                    query_string = data = preview_path = frame_path = image = None
            except ValueError:
                break

            if query_string is None:
                continue

            connection = None
            try:
                connection = self.conn_pool.getconn()
                with connection:
                    with connection.cursor() as curs:
                        #print(query_string.as_string(curs))
                        curs.execute(query_string, data)
                        record = curs.fetchone()
                        last_row = record[0]
                        self._save_image(preview_path, frame_path, image)
                event.notify('handler new object', last_row)
            except psycopg2.OperationalError:
                print(f'Transaction ({query_string}) is not committed')
            finally:
                if connection:
                    self.conn_pool.putconn(connection)

    def _save_image(self, preview_path, frame_path, image):
        preview_save_dir = os.path.join(self.image_dir, preview_path)
        frame_save_dir = os.path.join(self.image_dir, frame_path)
        preview_saved = cv2.imwrite(preview_save_dir, cv2.resize(image.image, (300, 150), cv2.INTER_NEAREST))
        frame_saved = cv2.imwrite(frame_save_dir, image.image)
        if not preview_saved or not frame_saved:
            print(f'ERROR: can\'t save image file {frame_save_dir}')

    def get_fields_names(self, table_name):
        if self.conn_pool is None:
            return None
        return self.tables[table_name].keys()

    def create_table(self, table_name):
        if self.conn_pool is None:
            return
        # self.query(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_name)))

        fields = [sql.SQL('count SERIAL PRIMARY KEY')]
        for key, value in self.tables[table_name].items():
            fields.append(sql.SQL("{} {}").format(sql.Identifier(key), sql.SQL(value)))

        create_table = sql.SQL("CREATE TABLE IF NOT EXISTS {table}({fields})").format(
            table=sql.Identifier(table_name),
            fields=sql.SQL(',').join(fields))
        self.query(create_table)

    def insert(self, table_name, data, preview_path, frame_path, image):
        if self.conn_pool is None:
            return
        fields = self.tables[table_name].keys()
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING count").format(
            sql.Identifier(table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((insert_query, data, preview_path, frame_path, image))
        # print(f'Put. Empty: {self.queue_in.get()}')

    def get_obj_info(self, table_name, obj_id):
        if self.conn_pool is None:
            return None

        query = sql.SQL("SELECT * from {} WHERE object_id = %s").format(sql.Identifier(table_name))
        return self.query(query, (obj_id,))

    def delete_obj(self, table_name, obj_id):
        if self.conn_pool is None:
            return

        del_query = sql.SQL("DELETE from {} WHERE object_id = %s").format(sql.Identifier(table_name))
        self.query(del_query, (obj_id,))

    def release_impl(self):
        pass

    def update(self, table_name, fields, obj_id, data):
        if self.conn_pool is None:
            return

        data = list(data)
        data.append(obj_id)
        data = tuple(data)
        last_obj_query = sql.SQL('''SELECT distinct on (object_id) count FROM {table} WHERE object_id = {id} 
                                    ORDER BY object_id, count DESC''').format(
            id=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(table_name))
        query = sql.SQL('UPDATE {table} SET {data} WHERE count=({selected}) RETURNING count, {fields}').format(
            table=sql.Identifier(table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Composed(last_obj_query),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        return self.query(query, data)

    # def append_info(self, table_name, fields, data):
    #     last_obj_query = sql.SQL('''SELECT distinct on (object_id) count FROM {table} WHERE object_id = {id}
    #                                         ORDER BY object_id, count DESC''').format(
    #         id=sql.Placeholder(),
    #         fields=sql.SQL(",").join(map(sql.Identifier, fields)),
    #         table=sql.Identifier(table_name))

    def has_default(self, table_name, field):
        if self.conn_pool is None:
            return False

        table = self.tables[table_name]
        if 'DEFAULT' not in table[field]:
            return False
        return True


if __name__ == '__main__':
    import json

    params_file = open('D:/Git/EvilEye/samples/visual_sample.json')
    parameters = json.load(params_file)
    db = DatabaseControllerPg()
    db.set_params(**parameters['database'])
    db.init()
    db.connect()
    # Uncomment, insert your path
    # load_folder = pathlib.Path(r'D:\Git\EvilEye\images\frames')
    # save_folder = pathlib.Path(r'D:\Git\EvilEye\images\frames\with_boxes')
    # utils.utils.draw_boxes_from_db(db, 'emerged', load_folder, save_folder)
    db.disconnect()

    # def query_impl(self):
    #     while self.run_flag:
    #         if self.conn_pool is None:
    #             break
    #
    #         try:
    #             if not self.queue_in.empty():
    #                 query_string, data = self.queue_in.get()
    #             else:
    #                 query_string, data = None, None
    #         except ValueError:
    #             break
    #
    #         connection = None
    #         try:
    #             connection = self.conn_pool.getconn()
    #             with connection:
    #                 with connection.cursor() as curs:
    #                     if query_string is not None:
    #                         print(query_string.as_string(curs))
    #                         curs.execute(query_string, data)
    #                         try:
    #                             result = curs.fetchall()
    #                         except psycopg2.ProgrammingError:
    #                             result = None
    #                     else:
    #                         result = None
    #             self.queue_out.put(result)
    #         except psycopg2.OperationalError:
    #             print(f'Transaction ({query_string}) is not committed')
    #         finally:
    #             if connection:
    #                 self.conn_pool.putconn(connection)
