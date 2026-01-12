"""
Поток для загрузки данных EventsJournal в фоновом режиме
"""

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtSql import QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    from PyQt5.QtSql import QSqlDatabase, QSqlQuery
    pyqt_version = 5

from ..core.logger import get_module_logger
import logging


class EventsJournalDataLoader(QThread):
    """Поток для загрузки данных EventsJournal в фоновом режиме"""
    
    # Сигналы для обновления прогресса и завершения
    progress_updated = pyqtSignal(str)  # stage_text
    data_ready = pyqtSignal(dict)  # loaded data: source_name_id_address, db_connection_name, etc.
    
    def __init__(self, db_controller, journal_adapters, table_name, params, database_params, table_params,
                 logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__()
        self.db_controller = db_controller
        self.journal_adapters = journal_adapters
        self.table_name = table_name
        self.params = params
        self.database_params = database_params
        self.table_params = table_params
        
        # Используем утилиту для обеспечения полноты database_params
        from evileye.utils.database_config_utils import ensure_database_config_complete
        self.database_params = ensure_database_config_complete(self.database_params)
        
        # Extract DB connection parameters with fallback to defaults
        db_section = self.database_params.get('database', {})
        self.db_params = (
            db_section.get('user_name', 'postgres'),
            db_section.get('password', ''),
            db_section.get('database_name', 'evil_eye_db'),
            db_section.get('host_name', 'localhost'),
            db_section.get('port', 5432),
            db_section.get('image_dir', 'EvilEyeData')
        )
        self.username, self.password, self.db_name, self.host, self.port, self.image_dir = self.db_params
        
        base_name = "evileye.events_journal_data_loader"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        
    def run(self):
        """Выполнить загрузку данных в фоновом потоке"""
        try:
            self.progress_updated.emit("Loading source mappings...")
            self.logger.info("Creating source name/id/address dictionary...")
            
            # Create source name/id/address dictionary (lightweight operation, no DB needed)
            source_name_id_address = self._create_dict_source_name_address_id()
            
            self.logger.info("Data loading completed successfully")
            
            # Emit loaded data
            # Note: DB connection will be created in main GUI thread
            self.data_ready.emit({
                'source_name_id_address': source_name_id_address,
                'error': None
            })
            
        except Exception as e:
            error_msg = f"Data loading error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.data_ready.emit({
                'error': error_msg
            })
    
    def _create_dict_source_name_address_id(self):
        """Create dictionary mapping source names to (source_id, address) tuples"""
        camera_address_id_name = {}
        sources_params = self.params.get('pipeline', {}).get('sources', [])
        
        for source in sources_params:
            address = source['camera']
            for src_id, src_name in zip(source['source_ids'], source['source_names']):
                camera_address_id_name[src_name] = (src_id, address)
        
        return camera_address_id_name
