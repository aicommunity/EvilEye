import os
import json
from typing import List, Dict, Tuple, Callable, Optional
from .journal_data_source import EventJournalDataSource
from ..core.logger import get_module_logger


class JsonLabelJournalDataSource(EventJournalDataSource):
    """
    Data source that reads events from objects_found.json and objects_lost.json
    stored under base_dir/YYYY_MM_DD/.
    """

    def __init__(self, base_dir: str):
        self.logger = get_module_logger("journal_data_source_json")
        self.base_dir = base_dir
        self.date_folder: Optional[str] = None
        self._cache: List[Dict] = []
        self._last_file_timestamps = {}  # Track file modification times

    def set_base_dir(self, base_dir: str) -> None:
        self.base_dir = base_dir
        self._cache = []

    def set_date(self, date_folder: Optional[str]) -> None:
        self.date_folder = date_folder
        self._cache = []
    
    def force_refresh(self) -> None:
        """Force refresh of cache by clearing timestamps"""
        self._last_file_timestamps.clear()
        self._cache.clear()

    def list_available_dates(self) -> List[str]:
        if not os.path.isdir(self.base_dir):
            return []
        images_dir = os.path.join(self.base_dir, 'images')
        if not os.path.isdir(images_dir):
            return []
        return sorted([d for d in os.listdir(images_dir)
                       if os.path.isdir(os.path.join(images_dir, d)) and d[:4].isdigit()])

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

    def _load_cache(self) -> None:
        """Load cache and track file timestamps"""
        dates = [self.date_folder] if self.date_folder else self.list_available_dates()[-7:]
        
        # Check if files have changed
        files_changed = False
        for d in dates:
            if not d:
                continue
            base = os.path.join(self.base_dir, 'images', d)
            fps = [
                os.path.join(base, 'objects_found.json'),
                os.path.join(base, 'objects_lost.json'),
                os.path.join(base, 'attribute_events_found.json'),
                os.path.join(base, 'attribute_events_finished.json'),
                os.path.join(base, 'system_events.json'),
            ]
            if any(self._check_file_changed(fp) for fp in fps):
                files_changed = True
        
        # Only reload if files have changed or cache is empty
        if files_changed or not self._cache:
            self._cache.clear()  # Clear cache to reload
            for d in dates:
                if not d:
                    continue
                base = os.path.join(self.base_dir, 'images', d)
                self._read_file(os.path.join(base, 'objects_found.json'), 'found', d)
                self._read_file(os.path.join(base, 'objects_lost.json'), 'lost', d)
                self._read_file(os.path.join(base, 'attribute_events_found.json'), 'attr_found', d)
                self._read_file(os.path.join(base, 'attribute_events_finished.json'), 'attr_lost', d)
                self._read_file(os.path.join(base, 'fov_events_found.json'), 'fov_found', d)
                self._read_file(os.path.join(base, 'fov_events_lost.json'), 'fov_lost', d)
                self._read_file(os.path.join(base, 'zone_events_entered.json'), 'zone_entered', d)
                self._read_file(os.path.join(base, 'zone_events_left.json'), 'zone_left', d)
                self._read_file(os.path.join(base, 'camera_events.json'), 'cam', d)
                self._read_file(os.path.join(base, 'system_events.json'), 'sys', d)
            # default sort: ts desc (robust to None)
            self._cache.sort(key=lambda e: (e.get('ts') or ''), reverse=True)

    def _read_file(self, filepath: str, event_type: str, date_folder: str) -> None:
        if not os.path.isfile(filepath):
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
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
                    self._cache.append(ev)
        except Exception as e:
            self.logger.error(f"Read error {filepath}: {e}")
            # ignore broken files
            pass

    def _map_item(self, item: Dict, event_type: str, date_folder: str, idx: int) -> Optional[Dict]:
        try:
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
                    'event_id': f"{date_folder}:{event_type}:{idx}",
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
                    'date_folder': date_folder,
                }
            elif event_type in ('attr_found', 'attr_lost'):
                return {
                    'event_id': f"{date_folder}:{event_type}:{idx}",
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
                    'date_folder': date_folder,
                }
            elif event_type in ('fov_found', 'fov_lost'):
                return {
                    'event_id': f"{date_folder}:{event_type}:{idx}",
                    'event_type': event_type,
                    'ts': timestamp,
                    'source_id': item.get('source_id'),
                    'object_id': item.get('object_id'),
                    'image_filename': item.get('preview_path'),
                    'date_folder': date_folder,
                }
            elif event_type in ('zone_entered', 'zone_left'):
                return {
                    'event_id': f"{date_folder}:{event_type}:{idx}",
                    'event_type': event_type,
                    'ts': timestamp,
                    'source_id': item.get('source_id'),
                    'object_id': item.get('object_id'),
                    'image_filename': item.get('preview_path'),
                    'bounding_box': item.get('box'),
                    'zone_coords': item.get('zone_coords'),
                    'date_folder': date_folder,
                }
            elif event_type == 'cam':
                return {
                    'event_id': f"{date_folder}:{event_type}:{idx}",
                    'event_type': event_type,
                    'ts': timestamp,
                    'camera_full_address': item.get('camera_full_address'),
                    'connection_status': item.get('connection_status'),
                    'date_folder': date_folder,
                }
            elif event_type == 'sys':
                return {
                    'event_id': f"{date_folder}:{event_type}:{idx}",
                    'event_type': event_type,
                    'ts': timestamp,
                    'system_event': item.get('event_type'),
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
        return items[start:end]

    def get_total(self, filters: Dict) -> int:
        self._load_cache()
        return len(self._apply_filters(self._cache, filters))

    def watch_live(self, callback: Callable[[List[Dict]], None]) -> None:
        # no-op for now
        pass

    def close(self) -> None:
        self._cache = []


