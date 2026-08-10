import os
import json
import hashlib
from typing import List, Dict, Tuple, Callable, Optional
from .journal_data_source import EventJournalDataSource
from ..core.logger import get_module_logger


class JsonLabelJournalDataSource(EventJournalDataSource):
    """
    Data source that reads events from objects_found.json and objects_lost.json
    stored under base_dir/Detections/YYYY-MM-DD/Metadata/ and events under
    base_dir/Events/YYYY-MM-DD/Metadata/.
    """

    def __init__(self, base_dir: str, params: Optional[Dict] = None):
        self.logger = get_module_logger("journal_data_source_json")
        self.base_dir = base_dir
        self.params = params or {}
        self.date_folder: Optional[str] = None
        self.date_from: Optional[str] = None
        self.date_to: Optional[str] = None
        self._cache: List[Dict] = []
        self._last_file_timestamps = {}  # Track file modification times
        self._source_name_id_address = {}
        self._failed_files = set()  # Track files that failed to parse (to avoid repeated attempts)
        self._request_generation = 0
        self._cache_loaded_generation = -1
        self._load_source_mappings()

    def set_base_dir(self, base_dir: str) -> None:
        if self.base_dir == base_dir:
            return
        self.base_dir = base_dir
        self._cache = []
        self._last_file_timestamps.clear()

    def set_date(self, date_folder: Optional[str]) -> None:
        if self.date_folder == date_folder and self.date_from is None and self.date_to is None:
            return
        self.date_folder = date_folder
        self.date_from = None
        self.date_to = None
        self._cache = []
        self._cache_loaded_generation = -1

    def set_date_range(self, date_from: Optional[str], date_to: Optional[str]) -> None:
        if self.date_from == date_from and self.date_to == date_to and self.date_folder is None:
            return
        self.date_folder = None
        self.date_from = date_from
        self.date_to = date_to
        self._cache = []
        self._cache_loaded_generation = -1

    def begin_request(self) -> None:
        """Mark start of API request so fetch/get_total share one cache load."""
        self._request_generation += 1

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

    def force_refresh(self) -> None:
        """Force refresh of cache by clearing timestamps"""
        self._last_file_timestamps.clear()
        self._cache.clear()

    def list_available_dates(self) -> List[str]:
        if not os.path.isdir(self.base_dir):
            return []
        # Check both Detections and Events directories for dates
        detections_dir = os.path.join(self.base_dir, 'Detections')
        events_dir = os.path.join(self.base_dir, 'Events')
        dates = set()
        if os.path.isdir(detections_dir):
            dates.update([d for d in os.listdir(detections_dir)
                          if os.path.isdir(os.path.join(detections_dir, d)) and d[:4].isdigit()])
        if os.path.isdir(events_dir):
            dates.update([d for d in os.listdir(events_dir)
                          if os.path.isdir(os.path.join(events_dir, d)) and d[:4].isdigit()])
        return sorted(list(dates))

    def _check_file_changed(self, filepath: str) -> bool:
        """Check if file has been modified since last check"""
        try:
            if not os.path.exists(filepath):
                return False

            current_mtime = os.path.getmtime(filepath)
            last_mtime = self._last_file_timestamps.get(filepath, 0)

            if current_mtime > last_mtime:
                self._last_file_timestamps[filepath] = current_mtime
                return True
            return False
        except Exception:
            return False

    def _metadata_files_for_date(self, date_folder: str) -> List[tuple[str, str, str]]:
        detections_metadata = os.path.join(self.base_dir, 'Detections', date_folder, 'Metadata')
        events_metadata = os.path.join(self.base_dir, 'Events', date_folder, 'Metadata')
        return [
            (os.path.join(detections_metadata, 'objects_found.json'), 'found', date_folder),
            (os.path.join(detections_metadata, 'objects_lost.json'), 'lost', date_folder),
            (os.path.join(events_metadata, 'attribute_events_found.json'), 'attr_found', date_folder),
            (os.path.join(events_metadata, 'attribute_events_finished.json'), 'attr_lost', date_folder),
            (os.path.join(events_metadata, 'fov_events_found.json'), 'fov_found', date_folder),
            (os.path.join(events_metadata, 'fov_events_lost.json'), 'fov_lost', date_folder),
            (os.path.join(events_metadata, 'zone_events_entered.json'), 'zone_entered', date_folder),
            (os.path.join(events_metadata, 'zone_events_left.json'), 'zone_left', date_folder),
            (os.path.join(events_metadata, 'camera_events.json'), 'cam', date_folder),
            (os.path.join(events_metadata, 'system_events.json'), 'sys', date_folder),
        ]

    def _purge_cache_for_file(self, filepath: str) -> None:
        self._cache = [entry for entry in self._cache if entry.get('_source_file') != filepath]

    def _load_cache(self) -> None:
        """Load cache and track file timestamps."""
        if self._cache_loaded_generation == self._request_generation and self._cache:
            return

        if self.date_folder:
            dates = [self.date_folder]
        elif self.date_from and self.date_to:
            dates = [
                d for d in self.list_available_dates()
                if self.date_from <= d <= self.date_to
            ]
        else:
            dates = self.list_available_dates()[-7:]

        changed_files: List[tuple[str, str, str]] = []
        for date_folder in dates:
            if not date_folder:
                continue
            for filepath, event_type, date in self._metadata_files_for_date(date_folder):
                if self._check_file_changed(filepath):
                    changed_files.append((filepath, event_type, date))

        if changed_files:
            for filepath, event_type, date_folder in changed_files:
                self._purge_cache_for_file(filepath)
                self._read_file(filepath, event_type, date_folder)
            self._cache.sort(key=lambda e: (e.get('ts') or ''), reverse=True)
        elif not self._cache:
            for date_folder in dates:
                if not date_folder:
                    continue
                for filepath, event_type, date in self._metadata_files_for_date(date_folder):
                    self._read_file(filepath, event_type, date)
            self._cache.sort(key=lambda e: (e.get('ts') or ''), reverse=True)

        self._cache_loaded_generation = self._request_generation

    def _read_file(self, filepath: str, event_type: str, date_folder: str) -> None:
        if not os.path.isfile(filepath):
            return

        # Skip files that previously failed to parse (unless file was modified)
        if filepath in self._failed_files:
            # Check if file was modified since last failure
            try:
                current_mtime = os.path.getmtime(filepath)
                if filepath in self._last_file_timestamps and current_mtime <= self._last_file_timestamps.get(filepath,
                                                                                                              0):
                    # File hasn't changed, skip it
                    return
                # File was modified, remove from failed list and try again
                self._failed_files.discard(filepath)
            except Exception:
                pass

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as json_err:
                    self.logger.warning(
                        f"JSON parse error in {filepath}: {json_err}. File may be corrupted or incomplete. Skipping file.")
                    # Mark file as failed
                    self._failed_files.add(filepath)
                    try:
                        self._last_file_timestamps[filepath] = os.path.getmtime(filepath)
                    except Exception:
                        pass
                    return

            # Handle different JSON structures
            if isinstance(data, list):
                # Direct array of objects
                items = data
            elif isinstance(data, dict) and 'objects' in data:
                # Objects in 'objects' array
                items = data['objects']
            else:
                # Single object or other structure
                items = [data] if data else []

            for idx, item in enumerate(items):
                ev = self._map_item(item, event_type, date_folder, idx)
                if ev:
                    ev['_source_file'] = filepath
                    self._cache.append(ev)
        except Exception as e:
            self.logger.error(f"Read error {filepath}: {e}")
            import traceback
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            # ignore broken files
            pass

    def _map_item(self, item: Dict, event_type: str, date_folder: str, idx: int) -> Optional[Dict]:
        try:
            # Use real event_id from JSON if available (preferred), otherwise generate from hash
            real_event_id = item.get('event_id')
            if real_event_id is not None:
                # Real event_id from JSON (matches DB event_id used in video filenames)
                event_id_numeric = int(real_event_id) if isinstance(real_event_id, (int, str)) else None
                event_id_str = f"{date_folder}:{event_type}:{real_event_id}"
            else:
                # Fallback: generate from hash for old data without event_id
                event_id_str = f"{date_folder}:{event_type}:{idx}"
                event_id_numeric = int(hashlib.md5(event_id_str.encode()).hexdigest()[:8], 16) % (10 ** 10)

            # Handle bounding box format (store raw for drawing)
            bbox = item.get('bounding_box', None)

            # Handle different timestamp fields for different event types
            if event_type == 'found':
                timestamp = item.get('timestamp') or item.get('ts')
            elif event_type == 'lost':
                timestamp = item.get('lost_timestamp') or item.get('ts')  # fallback to ts
            else:
                # For attr_*, fov_*, zone_*, cam, prefer 'ts' if present
                timestamp = item.get('timestamp') or item.get('ts')

            if event_type in ('found', 'lost'):
                return {
                    'event_id': event_id_str,
                    'event_id_numeric': event_id_numeric,
                    'event_type': event_type,
                    'ts': timestamp,
                    'source_id': item.get('source_id'),
                    'source_name': item.get('source_name'),
                    'object_id': item.get('object_id'),
                    'class_id': item.get('class_id'),
                    'class_name': item.get('class_name'),
                    'frame_id': item.get('frame_id'),
                    'image_filename': item.get('image_filename'),
                    'bounding_box': item.get('bounding_box') or bbox,
                    'confidence': item.get('confidence'),
                    'video_path': item.get('video_path'),  # If available in JSON
                    'video_path_lost': item.get('video_path_lost'),  # If available in JSON
                    'date_folder': date_folder,
                }
            elif event_type in ('attr_found', 'attr_lost'):
                # For attribute events, video_path depends on found/lost
                video_path_key = 'video_path_finished' if event_type == 'attr_lost' else 'video_path_found'
                return {
                    'event_id': event_id_str,
                    'event_id_numeric': event_id_numeric,
                    'event_type': event_type,
                    'ts': timestamp,
                    'source_id': item.get('source_id'),
                    'object_id': item.get('object_id'),
                    'class_id': item.get('class_id'),
                    'class_name': item.get('class_name'),
                    'image_filename': item.get('preview_path') or item.get('image_filename') or '',
                    'bounding_box': item.get('box'),
                    'attrs': item.get('attrs', []),
                    'event_name': item.get('event_name', ''),
                    'video_path': item.get('video_path_found') if event_type == 'attr_found' else None,
                    'video_path_lost': item.get('video_path_finished') if event_type == 'attr_lost' else None,
                    'date_folder': date_folder,
                }
            elif event_type in ('fov_found', 'fov_lost'):
                return {
                    'event_id': event_id_str,
                    'event_id_numeric': event_id_numeric,
                    'event_type': event_type,
                    'ts': timestamp,
                    'source_id': item.get('source_id'),
                    'object_id': item.get('object_id'),
                    'image_filename': item.get('preview_path'),
                    'video_path': item.get('video_path') if event_type == 'fov_found' else None,
                    'video_path_lost': item.get('video_path_lost') if event_type == 'fov_lost' else None,
                    'date_folder': date_folder,
                }
            elif event_type in ('zone_entered', 'zone_left'):
                # For zone events, video_path depends on entered/left
                source_id = item.get('source_id')
                source_name = item.get('source_name')
                # If source_name is missing, try to get it from _source_name_id_address
                if not source_name and source_id is not None:
                    for src_name, (src_id, address) in self._source_name_id_address.items():
                        if src_id == source_id:
                            source_name = src_name
                            break
                return {
                    'event_id': event_id_str,
                    'event_id_numeric': event_id_numeric,
                    'event_type': event_type,
                    'ts': timestamp,
                    'source_id': source_id,
                    'source_name': source_name,  # Ensure source_name is set
                    'object_id': item.get('object_id'),
                    'zone_id': item.get('zone_id'),  # zone_id exists in JSON data
                    'image_filename': item.get('preview_path'),
                    'bounding_box': item.get('box'),
                    'zone_coords': item.get('zone_coords'),
                    'video_path': item.get('video_path_entered') if event_type == 'zone_entered' else None,
                    'video_path_lost': item.get('video_path_left') if event_type == 'zone_left' else None,
                    'date_folder': date_folder,
                }
            elif event_type == 'cam':
                from evileye.utils.camera_event_label import sanitize_camera_event_record

                clean = sanitize_camera_event_record(
                    {
                        'camera_full_address': item.get('camera_full_address'),
                        'connection_status': item.get('connection_status'),
                        'source_names': item.get('source_names'),
                        'source_name': item.get('source_name'),
                    },
                    source_mappings=self._source_name_id_address,
                )
                return {
                    'event_id': event_id_str,
                    'event_id_numeric': event_id_numeric,
                    'event_type': event_type,
                    'ts': timestamp,
                    'camera_full_address': clean.get('camera_full_address'),
                    'connection_status': clean.get('connection_status'),
                    'source_id': None,  # Camera events don't have source_id
                    'source_name': clean.get('source_name'),
                    'source_names': clean.get('source_names') or clean.get('source_name'),
                    'video_path': None,  # Camera events don't have video
                    'video_path_lost': None,
                    'date_folder': date_folder,
                }
            elif event_type == 'sys':
                info = item.get('event_message') or item.get('event_type') or 'System event'
                if item.get('event_type') == 'SystemStart':
                    info = 'System started'
                elif item.get('event_type') == 'SystemStop':
                    info = 'System stopped'
                elif item.get('event_type') == 'CudaOutOfMemory':
                    info = item.get('event_message') or 'CUDA out of memory: detection disabled'
                return {
                    'event_id': event_id_str,
                    'event_id_numeric': event_id_numeric,
                    'event_type': event_type,
                    'ts': timestamp,
                    'system_event': item.get('event_type'),
                    'information': info,
                    'source_id': None,  # System events don't have source_id
                    'source_name': None,
                    'video_path': None,  # System events don't have video
                    'video_path_lost': None,
                    'date_folder': date_folder,
                }
        except Exception as e:
            self.logger.error(f"Element mapping error: {e}")
            return None

    def _apply_filters(self, items: List[Dict], filters: Dict) -> List[Dict]:
        if not filters:
            return items
        res = items
        if et := filters.get('event_type'):
            res = [e for e in res if e.get('event_type') == et]
        if sid := filters.get('source_id'):
            res = [e for e in res if e.get('source_id') == sid]
        if sname := filters.get('source_name'):
            res = [e for e in res if e.get('source_name') == sname]
        if snames := filters.get('source_names'):
            allowed = {str(name) for name in snames}
            res = [e for e in res if str(e.get('source_name') or '') in allowed]
        if journal_kind := filters.get('journal_kind'):
            if journal_kind == 'objects':
                res = [e for e in res if e.get('event_type') in ('found', 'lost')]
            elif journal_kind == 'events':
                res = [e for e in res if e.get('event_type') not in ('found', 'lost')]
        if cls := filters.get('class_name'):
            res = [e for e in res if e.get('class_name') == cls]
        if oid := filters.get('object_id'):
            res = [e for e in res if e.get('object_id') == oid]
        if dr := filters.get('date_folder'):
            res = [e for e in res if e.get('date_folder') == dr]
        return res

    def _apply_sort(self, items: List[Dict], sort: List[Tuple[str, str]]) -> List[Dict]:
        if not sort:
            return items
        for key, direction in reversed(sort):
            reverse = (direction.lower() == 'desc')

            # Handle None values properly for sorting
            def sort_key(e):
                value = e.get(key)
                if value is None:
                    return '' if reverse else 'zzz'  # Empty string for desc, 'zzz' for asc
                return str(value)

            items.sort(key=sort_key, reverse=reverse)
        return items

    def fetch(self, page: int, size: int, filters: Dict, sort: List[Tuple[str, str]]) -> List[Dict]:
        self._load_cache()
        items = self._apply_filters(self._cache, filters)
        items = self._apply_sort(items, sort)
        start = max(0, page * size)
        end = start + size
        page_items = items[start:end]
        return [{k: v for k, v in row.items() if k != '_source_file'} for row in page_items]

    def get_total(self, filters: Dict) -> int:
        self._load_cache()
        return len(self._apply_filters(self._cache, filters))

    def watch_live(self, callback: Callable[[List[Dict]], None]) -> None:
        # no-op for now
        pass

    def close(self) -> None:
        self._cache = []
