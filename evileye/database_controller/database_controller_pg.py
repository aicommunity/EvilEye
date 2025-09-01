import datetime
import json
import time
import cv2
from ..utils import utils
import psycopg2
import pathlib
import os
from ..utils import utils
from .database_controller_base import DatabaseControllerBase
from psycopg2 import sql
from psycopg2 import pool
import copy
from ..utils import threading_events

from timeit import default_timer as timer
# see https://ru.hexlet.io/blog/posts/python-postgresql


class DatabaseControllerPg(DatabaseControllerBase):
    new_project_created = False
    new_job_created = False
    cur_project_id = 0
    cur_job_id = 0

    def __init__(self, system_params, controller_type='Writer'):
        super().__init__(controller_type)
        self.configuration_info = system_params
        self.cameras_params = system_params.get('pipeline', {}).get('sources', dict())
        self.conn_pool = None
        self.user_name = ""
        self.password = ""
        self.database_name = ""
        self.host_name = ""
        self.port = 0
        self.admin_user_name = ""
        self.admin_password = ""
        self.create_new_project = False
        self.image_dir = None
        self.tables = None
        self.preview_height = 0
        self.preview_width = 0
        self.preview_size = (0, 0)

    def set_params_impl(self):
        self.user_name = self.params['user_name']
        self.password = self.params['password']
        self.database_name = self.params['database_name']
        self.host_name = self.params['host_name']
        self.port = self.params['port']
        self.admin_user_name = self.params.get('admin_user_name', 'postgres')
        self.admin_password = self.params.get('admin_password', '')
        self.image_dir = self.params['image_dir']
        self.create_new_project = self.params['create_new_project']
        self.tables = copy.deepcopy(self.params['tables'])
        self.preview_width = self.params.get('preview_width', 150)
        self.preview_height = self.params.get('preview_height', 100)
        self.preview_size = (self.preview_width, self.preview_height)

    def get_params_impl(self):
        params = dict()
        params['user_name'] = self.user_name
        params['password'] = self.password
        params['database_name'] = self.database_name
        params['host_name'] = self.host_name
        params['port'] = self.port
        params['admin_user_name'] = self.admin_user_name
        params['admin_password'] = self.admin_password
        params['image_dir'] = self.image_dir
        params['create_new_project'] = self.create_new_project
        params['tables'] = copy.deepcopy(self.tables)
        params['preview_width'] = self.preview_width
        params['preview_height'] = self.preview_height
        return params

    def get_cameras_params(self):
        return self.cameras_params

    def get_params(self):
        return self.params

    def default(self):
        self.params['user_name'] = "evil_eye_user"
        self.params['password'] = ""
        self.params['database_name'] = "evil_eye_db"
        self.params['host_name'] = "localhost"
        self.params['port'] = 5432
        self.params['admin_user_name'] = "postgres"
        self.params['admin_password'] = ""
        self.params['image_dir'] = utils.get_project_root()
        self.set_params_impl()

    def init_impl(self):
        self._create_db(self.params['database_name'])
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
            raise

        for table_name in self.tables.keys():
            self.create_table(table_name)

        project_id = 0
        if not DatabaseControllerPg.new_project_created:
            project_id = self._create_new_project()
            DatabaseControllerPg.new_project_created = True
            DatabaseControllerPg.cur_project_id = project_id

        if not DatabaseControllerPg.new_job_created:
            job_id = self._create_new_job(project_id)
            DatabaseControllerPg.new_job_created = True
            DatabaseControllerPg.cur_job_id = job_id

        self._insert_cam_info(self.cameras_params)

    def disconnect_impl(self):
        self.stop()
        if self.conn_pool:
            self.conn_pool.closeall()
            self.conn_pool = None

    def query_impl(self, query_string, data=None):
        if self.conn_pool is None:
            return None

        connection = None
        try:
            connection = self.conn_pool.getconn()
            with connection:
                with connection.cursor() as curs:
                    # print(query_string.as_string(curs))
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
            if self.conn_pool is None:
                continue

            try:
                if not self.queue_in.empty():
                    query_type, query_string, fields, data, preview_path, frame_path, image = self.queue_in.get()
                    if query_string is not None:
                        pass
                else:
                    query_type = query_string = data = preview_path = frame_path = image = None
            except ValueError:
                break

            if query_string is None:
                continue

            connection = None
            try:
                connection = self.conn_pool.getconn()
                with connection:
                    with connection.cursor() as curs:
                        curs.execute(query_string, data)
                        record = curs.fetchone()
                        row_num = record[0]
                        box = record[1]
                        start_save_it = timer()
                        self._save_image(preview_path, frame_path, image, box)
                        end_save_it = timer()
                start_notify_it = timer()
                if query_type == 'Insert':
                    threading_events.notify('handler new object', row_num)
                elif query_type == 'Update':
                    threading_events.notify('handler update object', row_num)
                end_notify_it = timer()
                # print(f'Notification:{end_notify_it-start_notify_it}; Saving:{end_save_it-start_save_it}')
            except psycopg2.OperationalError:
                print(f'Transaction ({query_string}) is not committed')
            finally:
                if connection:
                    self.conn_pool.putconn(connection)

    def _save_image(self, preview_path, frame_path, image, box):
        # Resolve relative image_dir path to current working directory for access
        image_dir_resolved = self.image_dir
        if not os.path.isabs(image_dir_resolved):
            image_dir_resolved = os.path.join(os.getcwd(), image_dir_resolved)
        
        preview_save_dir = os.path.join(image_dir_resolved, preview_path)
        frame_save_dir = os.path.join(image_dir_resolved, frame_path)
        preview = cv2.resize(copy.deepcopy(image.image), self.preview_size, cv2.INTER_NEAREST)
        preview_boxes = utils.utils.draw_preview_boxes(preview,
                                                       self.preview_width, self.preview_height, box)
        preview_saved = cv2.imwrite(preview_save_dir, preview_boxes)
        frame_saved = cv2.imwrite(frame_save_dir, image.image)
        if not preview_saved or not frame_saved:
            print(f'ERROR: can\'t save image file {frame_save_dir}')

    def get_fields_names(self, table_name):
        if self.conn_pool is None:
            return None
        return self.tables[table_name].keys()

    def _create_db(self, db_name):
        conn = None
        try:
            # Connect to postgres database using admin credentials to create new database
            conn = psycopg2.connect(dbname="postgres", user=self.admin_user_name,
                                    password=self.admin_password, host=self.host_name,
                                    port=self.port)
            conn.autocommit = True
            with conn.cursor() as curs:
                curs.execute(sql.SQL('SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s;'), (db_name,))
                db_exists = curs.fetchone()
                if not db_exists:
                    curs.execute(sql.SQL('CREATE DATABASE {database_name};').format(
                        database_name=sql.Identifier(db_name)))
                else:
                    print(f'Database {db_name} already exists')
        except psycopg2.OperationalError as exc:
            print(exc)
        finally:
            if conn:
                conn.close()

    def create_table(self, table_name):
        if self.conn_pool is None:
            return
        # self.query(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(table_name)))

        fields = []
        for key, value in self.tables[table_name].items():
            if key in ['PRIMARY KEY', 'FOREIGN KEY']:
                # pr_key_fields = value.strip('()').split(',')
                # fields.append(sql.SQL("PRIMARY KEY ({fields})").format(
                #     fields=sql.SQL(",").join(map(sql.Identifier, pr_key_fields))))
                fields.append(sql.SQL("{} {}").format(sql.SQL(key), sql.SQL(value)))
            else:
                fields.append(sql.SQL("{} {}").format(sql.Identifier(key), sql.SQL(value)))

        create_table = sql.SQL("CREATE TABLE IF NOT EXISTS {table}({fields})").format(
            table=sql.Identifier(table_name),
            fields=sql.SQL(',').join(fields))
        self.query(create_table)

    def insert(self, table_name, fields, data, preview_path, frame_path, image):
        if self.conn_pool is None:
            return
        query_type = 'Insert'
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING record_id, bounding_box").format(
            sql.Identifier(table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, fields, data, preview_path, frame_path, image))
        # print(f'Put. Empty: {self.queue_insert.get()}')

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

    def update(self, table_name, fields, data, obj_id, preview_path, frame_path, image):
        if self.conn_pool is None:
            return

        query_type = 'Update'
        data = list(data)
        data.append(obj_id)
        data = tuple(data)
        last_obj_query = sql.SQL('''SELECT distinct on (object_id) record_id FROM {table} WHERE object_id = {id} 
                                    ORDER BY object_id, record_id DESC''').format(
            id=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(table_name))
        update_query = sql.SQL('UPDATE {table} SET {data} WHERE record_id=({selected}) '
                               'RETURNING record_id, lost_bounding_box').format(
            table=sql.Identifier(table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Composed(last_obj_query),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        self.queue_in.put((query_type, update_query, fields, data, preview_path, frame_path, image))

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

    def _create_new_project(self):
        if not self.create_new_project:
            query = sql.SQL('SELECT max(project_id) from projects')
            project_id = self.query(query)[0][0]
            if project_id is not None:
                return project_id
        cur_time = datetime.datetime.now()
        query = sql.SQL('INSERT INTO projects (creation_time) VALUES (%s) RETURNING project_id')
        project_id = self.query(query, (cur_time,))[0][0]
        return project_id

    def _create_new_job(self, project_id):
        cur_time = datetime.datetime.now()
        select_query = sql.SQL('SELECT max(record_id) FROM objects')
        last_row = self.query(select_query)[0][0] if self.query(select_query)[0][0] else 0
        first_record = last_row + 1
        config = json.dumps(self.configuration_info)
        exists, last_job_id, config_id = self._check_if_config_exist(config)
        if exists:
            config = None
        query = sql.SQL('INSERT INTO jobs (creation_time, project_id, first_record, is_terminated,'
                        ' configuration_info, configuration_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING job_id')
        job_id = self.query(query, (cur_time, project_id, first_record, False, config, config_id))[0][0]
        return job_id

    def _insert_cam_info(self, params):
        values = []
        cur_time = datetime.datetime.now()
        for source_params in params:
            full_address = source_params['camera']
            short_address = full_address
            if source_params['source'] == 'VideoFile':
                if '/' in full_address:
                    short_address = full_address.split('/')[-1]
                else:
                    short_address = full_address.split('\\')[-1]
            source_ids = source_params['source_ids']
            roi = source_params['src_coords']
            values.append((full_address, short_address, source_ids, roi, cur_time))
        query = sql.SQL('INSERT INTO camera_information (full_address, short_address, sources, roi, creation_time) '
                        ' VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING')
        for value in values:
            self.query(query, value)

    def update_video_dur(self, source_video_dur):
        sources = source_video_dur.keys()
        for source in sources:
            print(source)
            if self.cameras_params[source]['source'] != 'VideoFile':
                continue
            full_address = self.cameras_params[source]['camera']
            query = sql.SQL('UPDATE camera_information SET video_dur_ms = %s WHERE full_address = %s')
            self.query(query, (source_video_dur[source], full_address))

    def save_job_configuration_info(self, config_info):
        job_id = self.get_job_id()
        config = json.dumps(config_info)
        exists, last_job_id, config_id = self._check_if_config_exist(config)
        if exists and last_job_id != job_id:
            config = None
        # Получаем номер последней записи в данном запуске
        update_query = sql.SQL('UPDATE jobs SET configuration_info = %s, configuration_id = %s WHERE job_id = %s;')
        data = (config, config_id, job_id)
        self.query(update_query, data)

    def _check_if_config_exist(self, config) -> tuple[bool, int | None, int]:
        binary_config = config
        query = sql.SQL('SELECT job_id, configuration_id FROM jobs WHERE configuration_info::jsonb = %s::jsonb'
                        ' AND configuration_id IS NOT NULL')
        data = (binary_config,)
        records = self.query(query, data)
        job_id = None
        if not records:
            select_query = sql.SQL('SELECT max(configuration_id) FROM jobs;')
            record = self.query(select_query)
            if not record:
                return False, None, 0
            config_id = record[0][0] + 1 if record[0][0] else 1
            return False, job_id, config_id
        job_id, config_id = records[0]
        return True, job_id, config_id

    @staticmethod
    def get_project_id():
        return DatabaseControllerPg.cur_project_id

    @staticmethod
    def get_job_id():
        return DatabaseControllerPg.cur_job_id


if __name__ == '__main__':
    import json

    params_file = open('D:/Git/EvilEye/samples/video_file.json')
    parameters = json.load(params_file)
    db = DatabaseControllerPg(parameters)
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
