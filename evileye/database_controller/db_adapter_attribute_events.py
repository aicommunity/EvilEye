import time
from .db_adapter import DatabaseAdapterBase
from .constants import QueryType, EventType
from ..utils import threading_events
from ..utils import utils
import copy
from psycopg2 import sql
from .event_image_writer import EventImageWriter


class DatabaseAdapterAttributeEvents(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)
        self._event_image_writer = EventImageWriter(
            "",
            150,
            100,
            db_controller=self.db_controller,
            db_params=self.db_params,
            logger=self.logger,
        )

    def set_params_impl(self):
        super().set_params_impl()
        # event_name must match AttributeEvent.get_name()
        self.event_name = self.params['event_name']

    def _insert_impl(self, event):
        fields, data, preview_path, frame_path = self._prepare_for_saving(event)
        query_type = QueryType.INSERT
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path, frame_path, getattr(event, 'img_found', None),
                           getattr(event, 'box_found', None)))

    def _update_impl(self, event):
        fields, data, preview_path, frame_path = self._prepare_for_updating(event)
        query_type = QueryType.UPDATE
        data.append(event.event_id)
        data = tuple(data)
        update_query = sql.SQL('UPDATE {table} SET {data} WHERE event_id=({selected})').format(
            table=sql.Identifier(self.table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        self.queue_in.put(
            (query_type, update_query, data, preview_path, frame_path, getattr(event, 'img_finished', None),
             getattr(event, 'box_finished', None)))

    def _process_queue_item(self, item):
        query_type, query_string, data, preview_path, frame_path, image, box = item

        if query_string is None:
            return

        try:
            self.db_controller.query(query_string, data)
        except Exception as e:
            should_retry, last_error = self.error_handler.handle_query_error(
                error=e,
                query_string=str(query_string) if query_string else None,
                retry_callback=None,
                max_retries=1,
            )
            if last_error:
                return
        try:
            if image is not None and preview_path is not None and frame_path is not None and box is not None:
                self._save_image(preview_path, frame_path, image, box)
        except Exception:
            pass
        if query_type == QueryType.INSERT:
            threading_events.notify(EventType.NEW_EVENT)
        elif query_type == QueryType.UPDATE:
            threading_events.notify(EventType.UPDATE_EVENT)

    def _prepare_for_saving(self, event) -> tuple[list, list, str, str]:
        # Payload with image paths for attribute event START
        fields_for_saving = {
            'event_id': event.event_id,
            'source_id': event.source_id,
            'time_stamp': event.timestamp,
            'time_finished': event.get_time_finished(),
            'object_id': event.object_id,
            'event_name': event.matched_event_name,
            'attrs': ','.join(event.matched_attrs),
            'class_id': event.class_id if event.class_id is not None else -1,
            'box_found': None,
            'box_finished': None,
            'preview_path_found': '',
            'frame_path_found': '',
            'video_path_found': getattr(event, 'video_path_found', None),
            'video_path_finished': None
        }
        # Normalize and set box_found if available
        if event.box_found is not None and event.img_found is not None and hasattr(event.img_found, 'image'):
            ih, iw, _ = event.img_found.image.shape
            box = list(event.box_found)
            norm_box = [box[0] / iw, box[1] / ih, box[2] / iw, box[3] / ih]
            fields_for_saving['box_found'] = norm_box
        preview_path = self._get_img_path('preview', 'attribute_found', event, event.time_found)
        frame_path = self._get_img_path('frame', 'attribute_found', event, event.time_found)
        fields_for_saving['preview_path_found'] = preview_path
        fields_for_saving['frame_path_found'] = frame_path
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()), preview_path, frame_path)

    def _prepare_for_updating(self, event):
        # Update finish timestamp and image paths on event completion
        fields_for_updating = {
            'time_finished': event.get_time_finished(),
            'box_finished': None,
            'preview_path_finished': self._get_img_path('preview', 'attribute_finished', event,
                                                        time_lost=event.get_time_finished()),
            'frame_path_finished': self._get_img_path('frame', 'attribute_finished', event,
                                                      time_lost=event.get_time_finished()),
            'video_path_finished': getattr(event, 'video_path_finished', None)
        }
        if event.box_finished is not None and event.img_finished is not None and hasattr(event.img_finished, 'image'):
            ih, iw, _ = event.img_finished.image.shape
            box = list(event.box_finished)
            norm_box = [box[0] / iw, box[1] / ih, box[2] / iw, box[3] / ih]
            fields_for_updating['box_finished'] = norm_box
        return (list(fields_for_updating.keys()), list(fields_for_updating.values()),
                fields_for_updating['preview_path_finished'], fields_for_updating['frame_path_finished'])

    def _save_image(self, preview_path, frame_path, image, box):
        self._event_image_writer.save(preview_path, frame_path, image, box=box, draw_boxes=False)

    def _get_img_path(self, image_type, obj_event_type, event, time_stamp=None, time_lost=None):
        save_dir = self.db_params['image_dir']
        events_dir = os.path.join(save_dir, 'Events')
        from evileye.core.event_time import date_folder_from_ts
        cur_date_str = date_folder_from_ts(time_lost if obj_event_type != 'attribute_found' else time_stamp)

        current_day_path = os.path.join(events_dir, cur_date_str)
        images_dir = os.path.join(current_day_path, 'Images')
        # New folders for events: FoundFrames/FoundPreviews/LostFrames/LostPreviews
        if obj_event_type == 'attribute_found':
            if image_type == 'preview':
                subdir = 'FoundPreviews'
            else:
                subdir = 'FoundFrames'
        else:  # attribute_finished
            if image_type == 'preview':
                subdir = 'LostPreviews'
            else:
                subdir = 'LostFrames'
        obj_type_path = os.path.join(images_dir, subdir)

        if not os.path.exists(events_dir):
            os.makedirs(events_dir, exist_ok=True)
        if not os.path.exists(current_day_path):
            os.makedirs(current_day_path, exist_ok=True)
        if not os.path.exists(images_dir):
            os.makedirs(images_dir, exist_ok=True)
        if not os.path.exists(obj_type_path):
            os.makedirs(obj_type_path, exist_ok=True)

        obj_id = event.object_id
        if obj_event_type == 'attribute_found':
            timestamp = (time_stamp or event.timestamp).strftime('%Y-%m-%d_%H-%M-%S.%f')
            img_path = os.path.join(obj_type_path,
                                    f'{timestamp}_attr_{event.matched_event_name}_obj{obj_id}_{image_type}.jpeg')
        elif obj_event_type == 'attribute_finished':
            ts = (time_lost or event.get_time_finished())
            timestamp = ts.strftime('%Y-%m-%d_%H-%M-%S-%f') if ts else 'unknown'
            img_path = os.path.join(obj_type_path,
                                    f'{timestamp}_attr_{event.matched_event_name}_obj{obj_id}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)

    # NOTE: schema migrations are applied centrally at DB startup (see `database_controller/migrations.py`).
