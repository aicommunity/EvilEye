import os
import datetime
from typing import List, Dict, Tuple, Callable, Optional
from .journal_data_source import EventJournalDataSource
from ..core.logger import get_module_logger

try:
    from PyQt6.QtSql import QSqlDatabase, QSqlQuery
    from PyQt6.QtCore import QDateTime, QVariant
    pyqt_version = 6
except ImportError:
    from PyQt5.QtSql import QSqlDatabase, QSqlQuery
    from PyQt5.QtCore import QDateTime, QVariant
    pyqt_version = 5


class DatabaseJournalDataSource(EventJournalDataSource):
    """
    Data source that reads events from PostgreSQL database.
    Works with both objects and events journals.
    """

    def __init__(self, db_controller, journal_type='objects', adapters=None, 
                 database_params=None, params=None, image_dir=None, 
                 db_connection_name='unified_conn'):
        """
        Args:
            db_controller: Database controller instance
            journal_type: 'objects' or 'events'
            adapters: List of JournalAdapterBase instances for events journal
            database_params: Database configuration parameters
            params: Application parameters (for source mappings)
            image_dir: Base directory for images
            db_connection_name: Qt SQL connection name
        """
        self.logger = get_module_logger("journal_data_source_db")
        self.db_controller = db_controller
        self.journal_type = journal_type
        self.adapters = adapters or []
        self.database_params = database_params or {}
        self.params = params or {}
        self.image_dir = image_dir or 'EvilEyeData'
        self.db_connection_name = db_connection_name
        
        self.date_filter: Optional[str] = None
        self._cache: List[Dict] = []  # Keep for compatibility, but won't be used for full load
        self._source_name_id_address = {}
        
        # Store QDateTime type for date conversion
        self._qdatetime_type = QDateTime
        self._qvariant_type = QVariant
        
        # Default time range: last 7 days (for pagination after initial load)
        self.default_days_back = 7
        
        # Initial load optimization: limit to last day, max 30 records
        self.initial_load_limit = 30
        self._is_initial_load = True
        
        # Initialize database connection
        self._init_db_connection()
        self._load_source_mappings()

    def _init_db_connection(self):
        """Initialize Qt SQL database connection"""
        # Use utility to ensure database_params completeness
        from evileye.utils.database_config_utils import ensure_database_config_complete
        self.database_params = ensure_database_config_complete(self.database_params)
        
        db_section = self.database_params.get('database', {})
        self.username = db_section.get('user_name', 'postgres')
        self.password = db_section.get('password', '')
        self.db_name = db_section.get('database_name', 'evil_eye_db')
        self.host = db_section.get('host_name', 'localhost')
        self.port = db_section.get('port', 5432)
        if not self.image_dir:
            self.image_dir = db_section.get('image_dir', 'EvilEyeData')
        
        # Check if connection already exists
        if self.db_connection_name in QSqlDatabase.connectionNames():
            return True
            
        db = QSqlDatabase.addDatabase("QPSQL", self.db_connection_name)
        db.setHostName(self.host)
        db.setDatabaseName(self.db_name)
        db.setUserName(self.username)
        db.setPassword(self.password)
        db.setPort(self.port)
        if not db.open():
            error_text = db.lastError().databaseText()
            self.logger.error(f"Database connection failed: {error_text}")
            return False
        return True

    def _load_source_mappings(self):
        """Load source name to (source_id, address) mappings"""
        try:
            sources_params = self.params.get('pipeline', {}).get('sources', [])
            for source in sources_params:
                address = source.get('camera', '')
                source_ids = source.get('source_ids', [])
                source_names = source.get('source_names', [])
                for src_id, src_name in zip(source_ids, source_names):
                    self._source_name_id_address[src_name] = (src_id, address)
        except Exception as e:
            self.logger.warning(f"Failed to load source mappings: {e}")

    def set_base_dir(self, base_dir: str) -> None:
        """Set base directory (for compatibility with EventJournalDataSource)"""
        self.image_dir = base_dir
        self._cache.clear()

    def set_date(self, date_folder: Optional[str]) -> None:
        """Set date filter"""
        self.date_filter = date_folder
        self._cache.clear()

    def force_refresh(self) -> None:
        """Force refresh of cache (no-op since we use on-demand loading)"""
        # Cache is no longer used for full data loading, so this is a no-op
        # Keeping for compatibility with interface
        self._cache.clear()

    def list_available_dates(self) -> List[str]:
        """List available dates from database"""
        if not self._init_db_connection():
            return []
        
        dates = set()
        query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
        
        if self.journal_type == 'objects':
            # Get dates from objects table
            query.prepare('SELECT DISTINCT DATE(time_stamp) as date FROM objects ORDER BY date DESC LIMIT 30')
        else:
            # Get dates from jobs table or events tables
            query.prepare('SELECT DISTINCT DATE(time_stamp) as date FROM jobs ORDER BY date DESC LIMIT 30')
        
        if query.exec():
            while query.next():
                date_val = query.value(0)
                if date_val:
                    if hasattr(date_val, 'toString'):
                        date_str = date_val.toString('yyyy-MM-dd')
                    else:
                        date_str = str(date_val)
                    dates.add(date_str)
        
        return sorted(list(dates), reverse=True)

    def _load_cache(self) -> None:
        """Load data from database into cache - DEPRECATED, kept for compatibility"""
        # This method is no longer used - data is loaded on-demand in fetch()
        # Keeping for backward compatibility
        pass

    # Old cache loading methods removed - data is now loaded on-demand with SQL pagination

    def _map_event_type(self, db_type: str) -> str:
        """Map database event type to JSON event type"""
        mapping = {
            'ZoneEvent': 'zone_entered',  # Will be paired with zone_left
            'AttributeEvent': 'attr_found',  # Will be paired with attr_lost
            'FOVEvent': 'fov_found',  # Will be paired with fov_lost
            'CameraEvent': 'cam',
            'SystemEvent': 'sys',
        }
        return mapping.get(db_type, db_type.lower())

    def _enrich_zone_event(self, event_dict: Dict, row_dict: Dict) -> None:
        """Enrich zone event with additional data from zone_events table"""
        query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
        # Note: zone_id doesn't exist in zone_events table, so we don't select it
        query.prepare('SELECT box_entered, box_left, zone_coords, object_id FROM zone_events WHERE preview_path_entered = :path OR preview_path_left = :path LIMIT 1')
        query.bindValue(':path', row_dict.get('preview_path', ''))
        if query.exec() and query.next():
            # Store in both formats for compatibility
            box_entered = self._parse_bbox(query.value(0))
            box_left = self._parse_bbox(query.value(1))
            event_dict['box_entered'] = box_entered
            event_dict['box_left'] = box_left
            event_dict['bounding_box'] = box_entered  # For backward compatibility
            event_dict['lost_bounding_box'] = box_left  # For backward compatibility
            event_dict['zone_coords'] = self._parse_zone_coords(query.value(2))
            event_dict['object_id'] = query.value(3)
            # zone_id doesn't exist in table, so we don't set it

    def _enrich_attribute_event(self, event_dict: Dict, row_dict: Dict) -> None:
        """Enrich attribute event with additional data"""
        query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
        query.prepare('SELECT box_found, box_finished, object_id, class_id, class_name, attrs, event_name FROM attribute_events WHERE preview_path_found = :path OR preview_path_finished = :path LIMIT 1')
        query.bindValue(':path', row_dict.get('preview_path', ''))
        if query.exec() and query.next():
            # Store in both formats for compatibility
            box_found = self._parse_bbox(query.value(0))
            box_finished = self._parse_bbox(query.value(1))
            event_dict['box_found'] = box_found
            event_dict['box_finished'] = box_finished
            event_dict['bounding_box'] = box_found  # For backward compatibility
            event_dict['lost_bounding_box'] = box_finished  # For backward compatibility
            event_dict['object_id'] = query.value(2)
            event_dict['class_id'] = query.value(3)
            event_dict['class_name'] = query.value(4)
            event_dict['attrs'] = self._parse_array(query.value(5))
            event_dict['event_name'] = query.value(6)

    def _enrich_fov_event(self, event_dict: Dict, row_dict: Dict) -> None:
        """Enrich FOV event with additional data"""
        query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
        query.prepare('SELECT object_id, source_id FROM fov_events WHERE preview_path = :path OR lost_preview_path = :path LIMIT 1')
        query.bindValue(':path', row_dict.get('preview_path', ''))
        if query.exec() and query.next():
            event_dict['object_id'] = query.value(0)
            event_dict['source_id'] = query.value(1)

    def _parse_bbox(self, value) -> Optional[List[float]]:
        """Parse bounding box from database format"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                s = value.replace('{', '').replace('}', '')
                parts = [p.strip() for p in s.split(',')]
                if len(parts) == 4:
                    return [float(p) for p in parts]
            elif isinstance(value, (list, tuple)):
                if len(value) == 4:
                    return [float(v) for v in value]
        except Exception:
            pass
        return None

    def _parse_zone_coords(self, value) -> Optional[List[Tuple[float, float]]]:
        """Parse zone coordinates from database format"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                s = value.strip('{}')
                points_str = [p.strip('{} ') for p in s.split('},')]
                coords = []
                for ps in points_str:
                    parts = [pp.strip() for pp in ps.split(',')]
                    if len(parts) == 2:
                        coords.append((float(parts[0]), float(parts[1])))
                return coords if coords else None
            elif isinstance(value, (list, tuple)):
                return [(float(p[0]), float(p[1])) for p in value if isinstance(p, (list, tuple)) and len(p) == 2]
        except Exception:
            pass
        return None

    def _parse_array(self, value) -> List:
        """Parse PostgreSQL array to Python list"""
        if value is None:
            return []
        try:
            if isinstance(value, str):
                s = value.strip('{}')
                return [p.strip() for p in s.split(',')] if s else []
            elif isinstance(value, (list, tuple)):
                return list(value)
        except Exception:
            pass
        return []

    def _build_objects_sql(self, filters: Dict, include_pagination: bool = False, page: int = 0, size: int = 50, initial_load: bool = False) -> str:
        """Build SQL query for objects with filters and optional pagination"""
        # Base SELECT
        sql = ('SELECT time_stamp, CAST(\'ObjectEvent\' AS text) AS event_type, '
               '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || ROUND(confidence::numeric, 2) AS information, '
               'source_name, time_lost, preview_path, lost_preview_path, object_id, class_id, confidence, '
               'bounding_box, lost_bounding_box, source_id, object_data '
               'FROM objects ')
        
        conditions = []
        
        # Date filter
        if self.date_filter:
            conditions.append(f"DATE(time_stamp) = '{self.date_filter}'")
        elif initial_load:
            # При начальной загрузке - только последний день
            today = datetime.datetime.now().date()
            conditions.append(f"DATE(time_stamp) = '{today.strftime('%Y-%m-%d')}'")
        else:
            # Default: last 7 days (for pagination)
            default_start = datetime.datetime.now() - datetime.timedelta(days=self.default_days_back)
            conditions.append(f"time_stamp >= '{default_start.strftime('%Y-%m-%d %H:%M:%S')}'")
        
        # Source name filter
        if filters.get('source_name'):
            source_name_escaped = filters['source_name'].replace("'", "''")
            conditions.append(f"source_name = '{source_name_escaped}'")
        
        # Source ID filter
        if filters.get('source_id'):
            conditions.append(f"source_id = {filters['source_id']}")
        
        # Object ID filter
        if filters.get('object_id'):
            conditions.append(f"object_id = {filters['object_id']}")
        
        # Class name filter (need to check object_data JSON)
        if filters.get('class_name'):
            # This is complex - would need JSON query, skip for now or do in Python
            pass
        
        if conditions:
            sql += 'WHERE ' + ' AND '.join(conditions)
        
        sql += ' ORDER BY time_stamp DESC'
        
        # Add pagination
        if include_pagination:
            if initial_load:
                # При начальной загрузке - только 30 записей
                sql += f' LIMIT {min(size, self.initial_load_limit)}'
            else:
                offset = page * size
                sql += f' LIMIT {size} OFFSET {offset}'
        
        return sql

    def _build_events_sql(self, filters: Dict, include_pagination: bool = False, page: int = 0, size: int = 50, initial_load: bool = False) -> str:
        """Build SQL query for events with filters and optional pagination"""
        if not self.adapters:
            return ''
        
        # Build UNION query from all adapters
        query_string = 'SELECT * FROM ('
        for adapter in self.adapters:
            adapter_query = adapter.select_query()
            query_string += adapter_query + ' UNION '
        query_string = query_string.removesuffix(' UNION ')
        query_string += ') AS temp '
        
        conditions = []
        
        # Date filter
        if self.date_filter:
            conditions.append(f"DATE(time_stamp) = '{self.date_filter}'")
        elif initial_load:
            # При начальной загрузке - только последний день
            today = datetime.datetime.now().date()
            conditions.append(f"DATE(time_stamp) = '{today.strftime('%Y-%m-%d')}'")
        else:
            # Default: last 7 days (for pagination)
            default_start = datetime.datetime.now() - datetime.timedelta(days=self.default_days_back)
            conditions.append(f"time_stamp >= '{default_start.strftime('%Y-%m-%d %H:%M:%S')}'")
        
        # Source name filter
        if filters.get('source_name'):
            source_name_escaped = filters['source_name'].replace("'", "''")
            conditions.append(f"source_name = '{source_name_escaped}'")
        
        if conditions:
            query_string += 'WHERE ' + ' AND '.join(conditions) + ' '
        
        query_string += 'ORDER BY time_stamp DESC'
        
        # Add pagination
        if include_pagination:
            if initial_load:
                # При начальной загрузке - только 30 записей
                query_string += f' LIMIT {min(size, self.initial_load_limit)}'
            else:
                offset = page * size
                query_string += f' LIMIT {size} OFFSET {offset}'
        
        return query_string

    def _convert_row_to_event(self, row_dict: Dict, is_found: bool = True) -> Dict:
        """Convert database row to unified event format"""
        time_stamp = row_dict.get('time_stamp') if is_found else row_dict.get('time_lost')
        
        if not time_stamp:
            return None
        
        # Extract date folder
        if isinstance(time_stamp, datetime.datetime):
            try:
                date_folder = time_stamp.strftime('%Y-%m-%d')
            except (ValueError, OverflowError):
                date_folder = self.date_filter or ''
        elif isinstance(time_stamp, str):
            date_folder = time_stamp.split()[0] if ' ' in time_stamp else time_stamp[:10]
        else:
            date_folder = self.date_filter or ''
        
        # Extract class_name from object_data
        class_name = ''
        object_data = row_dict.get('object_data')
        if object_data:
            try:
                import json
                if isinstance(object_data, str):
                    obj_data = json.loads(object_data)
                else:
                    obj_data = object_data
                class_name = obj_data.get('class_name', '') if isinstance(obj_data, dict) else ''
            except Exception:
                pass
        if not class_name:
            class_name = str(row_dict.get('class_id', ''))
        
        event_type = 'found' if is_found else 'lost'
        event_id = f"db:{event_type}:{row_dict.get('object_id', '')}:{time_stamp}"
        
        return {
            'event_id': event_id,
            'event_type': event_type,
            'ts': time_stamp,
            'source_id': row_dict.get('source_id'),
            'source_name': row_dict.get('source_name', ''),
            'object_id': row_dict.get('object_id'),
            'class_id': row_dict.get('class_id'),
            'class_name': class_name,
            'image_filename': row_dict.get('preview_path' if is_found else 'lost_preview_path', ''),
            'bounding_box': self._parse_bbox(row_dict.get('bounding_box' if is_found else 'lost_bounding_box')),
            'confidence': row_dict.get('confidence'),
            'date_folder': date_folder,
        }

    def _execute_query_and_convert(self, sql: str, skip_enrichment: bool = False) -> List[Dict]:
        """Execute SQL query and convert results to event format"""
        query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
        
        if not query.exec(sql):
            error_text = query.lastError().text()
            # Attempt to auto-migrate missing columns and retry once
            if 'does not exist' in error_text or 'UndefinedColumn' in error_text:
                try:
                    self._ensure_video_columns()
                    self.logger.warning('DB: Missing video columns detected. Applied auto-migration. Retrying query...')
                    # Retry query
                    query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
                    if not query.exec(sql):
                        self.logger.error(f"SQL Error after migration: {query.lastError().text()}")
                        return []
                except Exception as e:
                    self.logger.error(f"Failed to migrate video columns: {e}")
                    return []
            else:
                self.logger.error(f"SQL Error: {error_text}")
                return []
        
        results = []
        while query.next():
            record = query.record()
            row_dict = {}
            for i in range(record.count()):
                field_name = record.fieldName(i)
                value = query.value(i)
                
                # Convert Qt types to Python types
                if value is None:
                    row_dict[field_name] = None
                elif isinstance(value, self._qdatetime_type):
                    try:
                        if value.isValid():
                            row_dict[field_name] = value.toPyDateTime()
                        else:
                            row_dict[field_name] = None
                    except (ValueError, OverflowError):
                        row_dict[field_name] = None
                elif isinstance(value, self._qvariant_type):
                    if not value.isNull():
                        variant_value = value.value()
                        if isinstance(variant_value, self._qdatetime_type):
                            try:
                                if variant_value.isValid():
                                    row_dict[field_name] = variant_value.toPyDateTime()
                                else:
                                    row_dict[field_name] = None
                            except (ValueError, OverflowError):
                                row_dict[field_name] = None
                        else:
                            row_dict[field_name] = variant_value
                    else:
                        row_dict[field_name] = None
                elif isinstance(value, (int, float, bool)):
                    row_dict[field_name] = value
                else:
                    row_dict[field_name] = str(value)
            
            # For objects: create both found and lost events
            if self.journal_type == 'objects':
                # Found event
                if row_dict.get('time_stamp'):
                    found_event = self._convert_row_to_event(row_dict, is_found=True)
                    if found_event:
                        results.append(found_event)
                
                # Lost event
                if row_dict.get('time_lost'):
                    lost_event = self._convert_row_to_event(row_dict, is_found=False)
                    if lost_event:
                        results.append(lost_event)
            else:
                # For events: convert directly
                event_dict = self._convert_events_row_to_dict(row_dict, skip_enrichment=skip_enrichment)
                if event_dict:
                    results.append(event_dict)
        
        return results

    def _ensure_video_columns(self):
        """Ensure video columns exist in event tables"""
        try:
            from psycopg2 import sql as psql
            
            # Zone events
            self.db_controller.query(psql.SQL("ALTER TABLE zone_events ADD COLUMN IF NOT EXISTS video_path_entered text;"), None)
            self.db_controller.query(psql.SQL("ALTER TABLE zone_events ADD COLUMN IF NOT EXISTS video_path_left text;"), None)
            
            # Attribute events
            self.db_controller.query(psql.SQL("ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS video_path_found text;"), None)
            self.db_controller.query(psql.SQL("ALTER TABLE attribute_events ADD COLUMN IF NOT EXISTS video_path_finished text;"), None)
            
            # FOV events
            self.db_controller.query(psql.SQL("ALTER TABLE fov_events ADD COLUMN IF NOT EXISTS video_path text;"), None)
            self.db_controller.query(psql.SQL("ALTER TABLE fov_events ADD COLUMN IF NOT EXISTS video_path_lost text;"), None)
            
            self.logger.info("Video columns migration completed")
        except Exception as e:
            self.logger.error(f'DB: Failed to ensure video columns: {e}')

    def _convert_events_row_to_dict(self, row_dict: Dict, skip_enrichment: bool = False) -> Dict:
        """Convert events row to unified format"""
        event_type = row_dict.get('type', '')
        time_stamp = row_dict.get('time_stamp')
        
        if not time_stamp:
            return None
        
        # Extract date folder
        if isinstance(time_stamp, datetime.datetime):
            try:
                date_folder = time_stamp.strftime('%Y-%m-%d')
            except (ValueError, OverflowError):
                date_folder = self.date_filter or ''
        elif isinstance(time_stamp, str):
            date_folder = time_stamp.split()[0] if ' ' in time_stamp else time_stamp[:10]
        else:
            date_folder = self.date_filter or ''
        
        # Extract numeric event_id from row_dict (if available)
        event_id_numeric = row_dict.get('event_id')
        if event_id_numeric is not None:
            try:
                event_id_numeric = int(event_id_numeric)
            except (ValueError, TypeError):
                event_id_numeric = None
        
        event_dict = {
            'event_id': f"db:{event_type}:{time_stamp}",  # String ID for backward compatibility
            'event_id_numeric': event_id_numeric,  # Numeric ID from DB for video fragment lookup
            'event_type': self._map_event_type(event_type),
            'ts': time_stamp,
            'source_name': row_dict.get('source_name', ''),
            'source_id': row_dict.get('source_id'),  # Add source_id for video path resolution
            'information': row_dict.get('information', ''),
            'image_filename': row_dict.get('preview_path', ''),
            'time_lost': row_dict.get('time_lost'),
            'lost_preview_path': row_dict.get('lost_preview_path', ''),
            'video_path': row_dict.get('video_path'),  # Path to video fragment from DB
            'video_path_lost': row_dict.get('video_path_lost'),  # Path to lost video fragment from DB
            'date_folder': date_folder,
        }
        
        # Enrich with additional data based on event type (skip expensive enrichment during initial load)
        if event_type == 'ZoneEvent':
            # Extract object_id from row_dict (it's now in SQL SELECT)
            # zone_id doesn't exist in zone_events table, but we can generate it from zone_coords if available
            # This works even when skip_enrichment=True
            event_dict['object_id'] = row_dict.get('object_id')
            # Try to get zone_coords to generate zone_id (hash of coordinates)
            if not skip_enrichment:
                self._enrich_zone_event(event_dict, row_dict)
                # Generate zone_id from zone_coords if available
                if 'zone_coords' in event_dict and event_dict['zone_coords']:
                    import hashlib
                    coords_str = str(event_dict['zone_coords'])
                    zone_id = abs(hash(coords_str)) % 10000  # Generate ID from hash, limit to 4 digits
                    event_dict['zone_id'] = zone_id
            else:
                # During initial load, we don't have zone_coords, so zone_id will be None
                event_dict['zone_id'] = None
        elif event_type == 'AttributeEvent':
            if not skip_enrichment:
                self._enrich_attribute_event(event_dict, row_dict)
        elif event_type == 'FOVEvent':
            if not skip_enrichment:
                self._enrich_fov_event(event_dict, row_dict)
        elif event_type == 'CameraEvent':
            # CameraEvent enrichment is fast (no DB query), so always do it
            event_dict['camera_full_address'] = row_dict.get('source_name', '')
            event_dict['connection_status'] = 'reconnect' in (row_dict.get('information', '') or '').lower()
        elif event_type == 'SystemEvent':
            # SystemEvent enrichment is fast (no DB query), so always do it
            # Extract original event_type from information (which contains 'System started' or 'System stopped')
            information = row_dict.get('information', '')
            if information == 'System started':
                event_dict['system_event'] = 'SystemStart'
            else:
                event_dict['system_event'] = 'SystemStop'
        
        return event_dict

    def fetch(self, page: int, size: int, filters: Dict, sort: List[Tuple[str, str]]) -> List[Dict]:
        """Fetch page of events directly from database with SQL pagination"""
        try:
            # Check if this is initial load
            initial_load = self._is_initial_load and page == 0
            
            # Build SQL with filters and pagination
            if self.journal_type == 'objects':
                sql = self._build_objects_sql(filters, include_pagination=True, page=page, size=size, initial_load=initial_load)
            else:
                sql = self._build_events_sql(filters, include_pagination=True, page=page, size=size, initial_load=initial_load)
            
            # Reset initial load flag after first fetch
            if initial_load:
                self._is_initial_load = False
            
            if not sql:
                return []
            
            # Execute query and convert results (skip enrichment during initial load for events)
            results = self._execute_query_and_convert(sql, skip_enrichment=initial_load)
            
            # Apply remaining filters that can't be done in SQL (e.g., event_type for objects)
            if self.journal_type == 'objects' and filters.get('event_type'):
                results = [e for e in results if e.get('event_type') == filters['event_type']]
            
            # Apply sorting if needed (usually already sorted by SQL)
            if sort:
                for key, direction in reversed(sort):
                    reverse = (direction.lower() == 'desc')
                    def sort_key(e):
                        value = e.get(key)
                        if value is None:
                            return '' if reverse else 'zzz'
                        return str(value)
                    results.sort(key=sort_key, reverse=reverse)
            
            # For objects: limit results to requested page size
            # (since one DB row can produce 2 events, we might have more than size)
            if self.journal_type == 'objects' and len(results) > size:
                results = results[:size]
            
            return results
        except Exception as e:
            self.logger.error(f"Error fetching data: {e}", exc_info=True)
            return []

    def get_total(self, filters: Dict) -> int:
        """Get total count of events matching filters using COUNT(*)"""
        try:
            if self.journal_type == 'objects':
                # Build COUNT query for objects
                conditions = []
                
                # Date filter
                if self.date_filter:
                    conditions.append(f"DATE(time_stamp) = '{self.date_filter}'")
                else:
                    # Default: last 7 days
                    default_start = datetime.datetime.now() - datetime.timedelta(days=self.default_days_back)
                    conditions.append(f"time_stamp >= '{default_start.strftime('%Y-%m-%d %H:%M:%S')}'")
                
                # Source name filter
                if filters.get('source_name'):
                    source_name_escaped = filters['source_name'].replace("'", "''")
                    conditions.append(f"source_name = '{source_name_escaped}'")
                
                # Source ID filter
                if filters.get('source_id'):
                    conditions.append(f"source_id = {filters['source_id']}")
                
                # Object ID filter
                if filters.get('object_id'):
                    conditions.append(f"object_id = {filters['object_id']}")
                
                sql = 'SELECT COUNT(*) FROM objects'
                if conditions:
                    sql += ' WHERE ' + ' AND '.join(conditions)
                
                query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
                if not query.exec(sql):
                    self.logger.error(f"SQL Error in get_total: {query.lastError().text()}")
                    return 0
                
                if query.next():
                    count = query.value(0)
                    # For objects: each row can produce 1-2 events (found and/or lost)
                    # But for simplicity, we count rows. If needed, can be adjusted
                    base_count = int(count) if count is not None else 0
                    
                    # Apply event_type filter if set (this requires checking time_stamp/time_lost)
                    if filters.get('event_type'):
                        # Need to count separately for found/lost
                        # For now, return approximate count (will be filtered in fetch anyway)
                        return base_count
                    return base_count
            else:
                # Build COUNT query for events
                sql = self._build_events_sql(filters, include_pagination=False)
                if not sql:
                    return 0
                # Wrap in COUNT - remove ORDER BY and LIMIT
                base_sql = sql.split('ORDER BY')[0]
                sql = f'SELECT COUNT(*) FROM ({base_sql}) AS count_query'
                
                query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
                if not query.exec(sql):
                    self.logger.error(f"SQL Error in get_total: {query.lastError().text()}")
                    return 0
                
                if query.next():
                    count = query.value(0)
                    return int(count) if count is not None else 0
            
            return 0
        except Exception as e:
            self.logger.error(f"Error getting total: {e}", exc_info=True)
            return 0

    def watch_live(self, callback: Callable[[List[Dict]], None]) -> None:
        """Optional live updates (not implemented for DB source)"""
        pass

    def close(self) -> None:
        """Close data source and cleanup"""
        self._cache.clear()
        if self.db_connection_name in QSqlDatabase.connectionNames():
            QSqlDatabase.removeDatabase(self.db_connection_name)
