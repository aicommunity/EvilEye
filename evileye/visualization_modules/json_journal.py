import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PyQt6.QtCore import pyqtSignal

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from .journal_data_source_json import JsonLabelJournalDataSource
from .unified_objects_journal import UnifiedObjectsJournal
from .unified_events_journal import UnifiedEventsJournal
from ..core.logger import get_module_logger
import logging


class JsonJournalWindow(QWidget):
    def __init__(self, main_window, close_app: bool = False, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__()
        base_name = "evileye.json_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.main_window = main_window
        self.params = {}
        self.images_dir = None
        self.close_app = close_app
        
        # Инициализация пустого UI
        self.vis_params = {}
        self.obj_journal_enabled = True

        self.setWindowTitle('JSON Journal')
        self.resize(1600, 600)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
    
    def set_images_dir(self, images_dir, params):
        """Установить images_dir и params (вызывается после controller.init())"""
        self.images_dir = images_dir
        self.params = params
        
        # Get visualizer params
        self.vis_params = self.params.get('visualizer', {})
        self.obj_journal_enabled = self.vis_params.get('objects_journal_enabled', True)
        
        # Очищаем существующие вкладки
        while self.tabs.count() > 0:
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget:
                widget.deleteLater()
        
        # Add Objects journal tab (if enabled)
        if self.obj_journal_enabled:
            try:
                # Create JsonLabelJournalDataSource for objects
                objects_ds = JsonLabelJournalDataSource(self.images_dir, params=self.params)
                
                # Create UnifiedObjectsJournal
                objects_journal = UnifiedObjectsJournal(
                    objects_ds,
                    base_dir=self.images_dir,
                    parent=self,
                    logger_name="unified_objects_journal_json",
                    parent_logger=self.logger
                )
                self.tabs.addTab(objects_journal, 'Objects journal')
            except Exception as e:
                self.logger.error(f"Failed to create Objects journal: {e}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Add Events journal tab
        try:
            # Create JsonLabelJournalDataSource for events
            events_ds = JsonLabelJournalDataSource(self.images_dir, params=self.params)
            
            # Create UnifiedEventsJournal
            events_journal_widget = UnifiedEventsJournal(
                events_ds,
                base_dir=self.images_dir,
                parent=self,
                logger_name="unified_events_journal_json",
                parent_logger=self.logger
            )
            self.tabs.addTab(events_journal_widget, 'Events journal')
        except Exception as e:
            self.logger.error(f"Failed to create Events journal: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    def _close_tab(self, index):
        """Handle tab close request: hide tab but keep widget for quick restore"""
        widget = self.tabs.widget(index)
        if widget:
            widget.close()
        try:
            self.tabs.setTabVisible(index, False)
        except Exception:
            self.tabs.removeTab(index)
        # Hide window if all tabs are hidden/not visible
        try:
            any_visible = False
            bar = self.tabs.tabBar()
            # If tabBar has isTabVisible API
            if hasattr(bar, 'isTabVisible'):
                for i in range(self.tabs.count()):
                    if bar.isTabVisible(i):
                        any_visible = True
                        break
            else:
                # Fallback: if there are tabs, consider them visible
                any_visible = self.tabs.count() > 0
            if not any_visible:
                self.hide()
        except Exception:
            # Final fallback on count
            if self.tabs.count() == 0:
                self.hide()

    def _ensure_default_tabs(self):
        """Recreate default tabs when none exist (after user closed them)."""
        if not self.images_dir:
            return
        if self.tabs.count() > 0:
            return
        # Recreate Objects (if enabled)
        if self.obj_journal_enabled:
            try:
                objects_ds = JsonLabelJournalDataSource(self.images_dir, params=self.params)
                objects_journal = UnifiedObjectsJournal(
                    objects_ds,
                    base_dir=self.images_dir,
                    parent=self,
                    logger_name="unified_objects_journal_json",
                        parent_logger=self.logger
                )
                self.tabs.addTab(objects_journal, 'Objects journal')
            except Exception as e:
                self.logger.error(f"Failed to recreate Objects journal: {e}")
        # Recreate Events
        try:
            events_ds = JsonLabelJournalDataSource(self.images_dir, params=self.params)
            events_journal = UnifiedEventsJournal(
                events_ds,
                base_dir=self.images_dir,
                parent=self,
                logger_name="unified_events_journal_json",
                    parent_logger=self.logger
            )
            self.tabs.addTab(events_journal, 'Events journal')
        except Exception as e:
            self.logger.error(f"Failed to recreate Events journal: {e}")

        # Ensure tabs are visible
        try:
            for i in range(self.tabs.count()):
                try:
                    self.tabs.setTabVisible(i, True)
                except Exception:
                    pass
            try:
                self.tabs.tabBar().setVisible(True)
            except Exception:
                pass
        except Exception:
            pass

    def ensure_tab(self, title: str):
        """Ensure a tab with given title exists; create if missing and return its index."""
        if not self.images_dir:
            return -1
        # Check existing
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).lower().startswith(title.lower()):
                try:
                    self.tabs.setTabVisible(i, True)
                except Exception:
                    pass
                return i
        # Create if missing
        try:
            if title.lower().startswith('objects'):
                objects_ds = JsonLabelJournalDataSource(self.images_dir, params=self.params)
                widget = UnifiedObjectsJournal(
                    objects_ds,
                    base_dir=self.images_dir,
                    parent=self,
                    logger_name="unified_objects_journal_json_dyn",
                    parent_logger=self.logger
                )
                idx = self.tabs.addTab(widget, 'Objects journal')
                # Don't call _reload_table() here - widget will load data on first show via showEvent
                try:
                    self.tabs.setTabVisible(idx, True)
                except Exception:
                    pass
                return idx
            if title.lower().startswith('events'):
                events_ds = JsonLabelJournalDataSource(self.images_dir, params=self.params)
                widget = UnifiedEventsJournal(
                    events_ds,
                    base_dir=self.images_dir,
                    parent=self,
                    logger_name="unified_events_journal_json_dyn",
                    parent_logger=self.logger
                )
                idx = self.tabs.addTab(widget, 'Events journal')
                # Don't call _reload_table() here - widget will load data on first show via showEvent
                try:
                    self.tabs.setTabVisible(idx, True)
                except Exception:
                    pass
                return idx
        except Exception as e:
            self.logger.error(f"Failed to recreate '{title}' tab: {e}")
        return -1

    def showEvent(self, event):
        """Handle show event"""
        super().showEvent(event)
        # If all tabs were closed previously, recreate defaults
        self._ensure_default_tabs()
        # Make sure tab bar is visible
        try:
            self.tabs.tabBar().setVisible(True)
        except Exception:
            pass
        # If there are tabs but no current, set to first
        if self.tabs.count() > 0 and self.tabs.currentIndex() < 0:
            self.tabs.setCurrentIndex(0)
        # Don't reload all tabs here - they will load data on first show via showEvent
        # This prevents unnecessary data loading when switching tabs or showing window

    def closeEvent(self, event):
        """Handle close event"""
        self.hide()
        event.ignore()  # Don't actually close, just hide
