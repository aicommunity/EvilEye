import datetime
import json
try:
    from PyQt6.QtCore import QDate, QDateTime
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QLineEdit, QTableView, QStyledItemDelegate,
        QMessageBox, QTextEdit, QFormLayout, QSizePolicy, QComboBox, QCheckBox,
        QGroupBox, QMenu, QSplitter, QTabWidget, QProgressBar,
        QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem
    )
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QDate, QDateTime
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QLineEdit, QTableView, QStyledItemDelegate,
        QMessageBox, QTextEdit, QFormLayout, QSizePolicy, QComboBox, QCheckBox,
        QGroupBox, QMenu, QAction, QSplitter, QTabWidget, QProgressBar,
        QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QFont
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5
from . import parameters_processing
from ..dialogs import ConfigRestoreDialog, ConfigCompareDialog, JobDetailsDialog, ExportHistoryDialog
from ...database.config_history_manager import ConfigHistoryManager


class DateTimeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        # Обрабатываем как строку, так как данные приходят из ConfigHistoryManager
        if isinstance(value, str):
            return value
        elif hasattr(value, 'toString'):
            return value.toString(Qt.DateFormat.ISODate)
        else:
            return str(value)


class ParamsWindow(QWidget):
    def __init__(self):
        super().__init__(parent=None)
        self.setWindowTitle('Parameters')
        self.setFixedSize(900, 600)
        self.image_path = None
        self.text = QTextEdit()
        self.save_button = QPushButton('Save parameters', self)
        self.save_button.clicked.connect(self._save_data)
        self.file_name = QLabel('Enter file name')
        self.file_name_edit = QTextEdit()
        self.file_name_edit.setText('.json')
        self.file_name_edit.setFixedHeight(self.save_button.geometry().height())
        self.h_layout = QHBoxLayout()
        self.h_layout.addWidget(self.file_name)
        self.h_layout.addWidget(self.file_name_edit)
        self.h_layout.addWidget(self.save_button)

        self.main_layout = QVBoxLayout()
        self.main_layout.addWidget(self.text)
        self.main_layout.addLayout(self.h_layout)
        self.setLayout(self.main_layout)
        self.setVisible(False)

    def set_data(self, json_dict):
        editable_json = json.dumps(json_dict, indent=4)
        self.text.setText(editable_json)
        self.setVisible(True)

    @pyqtSlot()
    def _save_data(self):
        file_name = self.file_name_edit.toPlainText()
        if not file_name.strip('.json'):
            file_name = 'temp.json'
        json_str = self.text.toPlainText()
        json_dict = json.loads(json_str)
        with open(file_name, 'w') as file:
            json.dump(json_dict, file, indent=4)
        self.close()


class JobsHistory(QWidget):
    retrieve_data_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__()
        self.setMinimumSize(1280, 720)

        self.last_row_db = 0
        self.data_for_update = []
        self.last_update_time = None
        self.update_rate = 10
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        self.start_time_updated = False
        self.finish_time_updated = False
        self.block_updates = False
        self.params_win = ParamsWindow()
        
        # Новые атрибуты для улучшенной функциональности
        self.selected_jobs = []
        self.current_project_id = None
        self.filter_status = "All"  # All, Running, Stopped, Error
        self.filter_project = "All"
        
        # Флаг для предотвращения повторной загрузки данных
        self.data_loaded = False
        # Флаг для предотвращения рекурсии в фильтрах
        self.updating_filters = False

        self._setup_ui()
        
        # Инициализируем ConfigHistoryManager
        self.config_history_manager = None
    
    def _setup_ui(self):
        """Настройка пользовательского интерфейса"""
        # Основной layout создаем в начале
        self.main_layout = QVBoxLayout()
        
        self._setup_table()
        self._setup_filters()
        self._setup_projects_management()
        self._setup_time_layout()
        self._setup_config_buttons()
        
        # Добавляем управление проектами
        self.main_layout.addWidget(self.projects_group)
        
        # Добавляем фильтры
        self.main_layout.addWidget(self.filters_group)
        
        # Добавляем временные фильтры
        self.main_layout.addLayout(self.time_layout)
        
        # Добавляем таблицу
        self.main_layout.addWidget(self.table)
        
        # Добавляем кнопки для работы с конфигурациями
        self.main_layout.addLayout(self.config_buttons_layout)
        
        self.setLayout(self.main_layout)

        self.retrieve_data_signal.connect(self._retrieve_data)
        self.table.doubleClicked.connect(self._display_params)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
    
    def _setup_projects_management(self):
        """Настройка управления проектами"""
        self.projects_group = QGroupBox("Управление проектами")
        projects_layout = QVBoxLayout(self.projects_group)
        
        # Верхняя панель с выбором проекта
        top_layout = QHBoxLayout()
        
        # Выбор текущего проекта
        top_layout.addWidget(QLabel("Текущий проект:"))
        self.current_project_combo = QComboBox()
        self.current_project_combo.setMinimumWidth(200)
        self.current_project_combo.currentTextChanged.connect(self._on_current_project_changed)
        top_layout.addWidget(self.current_project_combo)
        
        # Кнопки управления проектами
        self.create_project_btn = QPushButton("Создать проект")
        self.create_project_btn.clicked.connect(self._create_new_project)
        top_layout.addWidget(self.create_project_btn)
        
        self.edit_project_btn = QPushButton("Редактировать")
        self.edit_project_btn.clicked.connect(self._edit_current_project)
        top_layout.addWidget(self.edit_project_btn)
        
        self.delete_project_btn = QPushButton("Удалить")
        self.delete_project_btn.clicked.connect(self._delete_current_project)
        top_layout.addWidget(self.delete_project_btn)
        
        self.refresh_projects_btn = QPushButton("Обновить")
        self.refresh_projects_btn.clicked.connect(self._refresh_projects_list)
        top_layout.addWidget(self.refresh_projects_btn)
        
        top_layout.addStretch()
        projects_layout.addLayout(top_layout)
        
        # Нижняя панель со статистикой проекта
        stats_layout = QHBoxLayout()
        
        # Статистика проекта
        self.project_stats_label = QLabel("Статистика проекта не загружена")
        self.project_stats_label.setStyleSheet("color: #666; font-style: italic;")
        stats_layout.addWidget(self.project_stats_label)
        
        # Кнопка детальной статистики
        self.project_stats_btn = QPushButton("Детальная статистика")
        self.project_stats_btn.clicked.connect(self._show_project_statistics)
        stats_layout.addWidget(self.project_stats_btn)
        
        stats_layout.addStretch()
        projects_layout.addLayout(stats_layout)
        
        # Инициализируем список проектов
        self._refresh_projects_list()
    
    def _setup_filters(self):
        """Настройка фильтров"""
        self.filters_group = QGroupBox("Фильтры")
        filters_layout = QHBoxLayout(self.filters_group)
        
        # Фильтр по проекту
        filters_layout.addWidget(QLabel("Проект:"))
        self.project_filter = QComboBox()
        self.project_filter.addItems(["Все проекты"])
        self.project_filter.currentTextChanged.connect(self._on_project_filter_changed)
        filters_layout.addWidget(self.project_filter)
        
        # Фильтр по статусу
        filters_layout.addWidget(QLabel("Статус:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Все", "Running", "Stopped", "Error"])
        self.status_filter.currentTextChanged.connect(self._on_status_filter_changed)
        filters_layout.addWidget(self.status_filter)
        
        # Поиск
        filters_layout.addWidget(QLabel("Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по ID, конфигурации...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        filters_layout.addWidget(self.search_edit)
        
        # Кнопка сброса фильтров
        self.reset_filters_btn = QPushButton("Сбросить фильтры")
        self.reset_filters_btn.clicked.connect(self._reset_filters)
        filters_layout.addWidget(self.reset_filters_btn)
        
        filters_layout.addStretch()
    
    def _setup_context_menu(self):
        """Настройка контекстного меню"""
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, position):
        """Показать контекстное меню"""
        if not self.table.indexAt(position).isValid():
            return
        
        menu = QMenu(self)
        
        # Действия для выбранных элементов
        view_details_action = QAction("Просмотр деталей", self)
        view_details_action.triggered.connect(self._view_job_details)
        menu.addAction(view_details_action)
        
        view_config_action = QAction("Просмотр конфигурации", self)
        view_config_action.triggered.connect(self._view_configuration)
        menu.addAction(view_config_action)
        
        menu.addSeparator()
        
        restore_action = QAction("Восстановить конфигурацию", self)
        restore_action.triggered.connect(self._on_restore_config_clicked)
        menu.addAction(restore_action)
        
        compare_action = QAction("Сравнить конфигурации", self)
        compare_action.triggered.connect(self._on_compare_configs_clicked)
        menu.addAction(compare_action)
        
        menu.addSeparator()
        
        export_action = QAction("Экспорт выбранных", self)
        export_action.triggered.connect(self._export_selected)
        menu.addAction(export_action)
        
        delete_action = QAction("Удалить задачу", self)
        delete_action.triggered.connect(self._delete_selected_jobs)
        menu.addAction(delete_action)
        
        menu.exec(self.table.mapToGlobal(position))
    
    def _view_job_details(self):
        """Просмотр деталей задачи"""
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return
        
        row = selection[0].row()
        if hasattr(self.model, 'data_list') and row < len(self.model.data_list):
            job_data = self.model.data_list[row]
            
            # Создаем диалог деталей задачи
            dialog = JobDetailsDialog(job_data, self)
            dialog.exec()
    
    def _view_configuration(self):
        """Просмотр конфигурации"""
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return
        
        row = selection[0].row()
        if hasattr(self.model, 'data_list') and row < len(self.model.data_list):
            job_data = self.model.data_list[row]
            config_info = job_data.get('configuration_info', {})
            
            if config_info:
                self.params_win.set_data(config_info)
            else:
                QMessageBox.information(self, "Информация", "Конфигурация недоступна для этого элемента.")
    
    def _export_selected(self):
        """Экспорт выбранных задач"""
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите задачи для экспорта.")
            return
        
        # Получаем данные выбранных задач
        selected_data = []
        for selected_row in selection:
            row = selected_row.row()
            if hasattr(self.model, 'data_list') and row < len(self.model.data_list):
                selected_data.append(self.model.data_list[row])
        
        if not selected_data:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить данные выбранных задач.")
            return
        
        # Показываем диалог сохранения файла
        if pyqt_version == 6:
            from PyQt6.QtWidgets import QFileDialog
        else:
            from PyQt5.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт выбранных задач",
            f"selected_jobs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON файлы (*.json);;Все файлы (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(selected_data, f, indent=2, ensure_ascii=False, default=str)
                
                QMessageBox.information(
                    self,
                    "Успех",
                    f"Выбранные задачи экспортированы в файл:\n{file_path}\n\n"
                    f"Задач экспортировано: {len(selected_data)}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Ошибка экспорта",
                    f"Не удалось экспортировать данные:\n{e}"
                )
    
    def _delete_selected_jobs(self):
        """Удаление выбранных задач"""
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return
        
        # Подтверждение удаления
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить {len(selection)} выбранных задач?\n\n"
            "Это действие нельзя отменить.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Здесь должна быть логика удаления задач из БД
            QMessageBox.information(
                self,
                "Удаление завершено",
                f"Удалено задач: {len(selection)}"
            )
            
            # Обновляем данные
            self._load_data()
    
    def _on_project_filter_changed(self, project_name):
        """Обработчик изменения фильтра проекта"""
        self.filter_project = project_name
        self._apply_filters()
    
    def _on_status_filter_changed(self, status):
        """Обработчик изменения фильтра статуса"""
        self.filter_status = status
        self._apply_filters()
    
    def _on_search_changed(self, search_text):
        """Обработчик изменения поискового запроса"""
        self._apply_filters()
    
    def _apply_filters(self):
        """Применить фильтры к данным"""
        if not hasattr(self.model, 'data_list'):
            return
        
        # Здесь должна быть логика фильтрации данных
        # Пока просто обновляем отображение
        self.model.update_data(self.model.data_list)
    
    def _reset_filters(self):
        """Сбросить все фильтры"""
        self.project_filter.setCurrentText("Все проекты")
        self.status_filter.setCurrentText("Все")
        self.search_edit.clear()
        self.filter_project = "All"
        self.filter_status = "All"
        self._apply_filters()

    def _setup_table(self):
        self.table = QTableView()
        self._setup_model()
        self.table.setModel(self.model)
        header = self.table.verticalHeader()
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.date_delegate = DateTimeDelegate(None)
        self.table.setItemDelegateForColumn(3, self.date_delegate)

    def _setup_model(self):
        # Используем стандартную модель таблицы вместо SQL модели
        from PyQt6.QtCore import QAbstractTableModel, Qt
        from PyQt6.QtGui import QFont
        
        class ConfigHistoryTableModel(QAbstractTableModel):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.data_list = []
                self.headers = ['Project ID', 'Job ID', 'Config ID', 'Status', 'Creation Time', 'Finish Time', 'Duration', 'Frames', 'Objects', 'Events', 'Configuration Info']
            
            def rowCount(self, parent=None):
                return len(self.data_list)
            
            def columnCount(self, parent=None):
                return len(self.headers)
            
            def data(self, index, role=Qt.ItemDataRole.DisplayRole):
                if not index.isValid():
                    return None
                
                row = index.row()
                col = index.column()
                
                if row >= len(self.data_list):
                    return None
                
                item = self.data_list[row]
                
                if role == Qt.ItemDataRole.DisplayRole:
                    if col == 0:
                        return str(item.get('project_id', ''))
                    elif col == 1:
                        return str(item.get('job_id', ''))
                    elif col == 2:
                        return str(item.get('configuration_id', ''))
                    elif col == 3:
                        return str(item.get('status', 'Unknown'))
                    elif col == 4:
                        creation_time = item.get('creation_time', '')
                        if creation_time:
                            if isinstance(creation_time, str):
                                return creation_time
                            else:
                                return creation_time.strftime("%Y-%m-%d %H:%M:%S")
                        return ''
                    elif col == 5:
                        finish_time = item.get('finish_time', '')
                        if finish_time:
                            if isinstance(finish_time, str):
                                return finish_time
                            else:
                                return finish_time.strftime("%Y-%m-%d %H:%M:%S")
                        return ''
                    elif col == 6:
                        # Вычисляем длительность
                        creation_time = item.get('creation_time')
                        finish_time = item.get('finish_time')
                        if creation_time and finish_time:
                            try:
                                if isinstance(creation_time, str):
                                    creation_time = datetime.datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                                if isinstance(finish_time, str):
                                    finish_time = datetime.datetime.fromisoformat(finish_time.replace('Z', '+00:00'))
                                
                                duration = finish_time - creation_time
                                return str(duration)
                            except:
                                return ''
                        return ''
                    elif col == 7:
                        return str(item.get('processed_frames', item.get('total_frames', '')))
                    elif col == 8:
                        return str(item.get('detected_objects', ''))
                    elif col == 9:
                        return str(item.get('detected_events', ''))
                    elif col == 10:
                        config_info = item.get('configuration_info', {})
                        if isinstance(config_info, dict):
                            return f"Config: {len(config_info)} sections"
                        return str(config_info)
                
                elif role == Qt.ItemDataRole.BackgroundRole:
                    # Цветовое кодирование по статусу
                    status = item.get('status', 'Unknown')
                    if status == 'Running':
                        return QColor(200, 255, 200)  # Светло-зеленый
                    elif status == 'Stopped':
                        return QColor(200, 200, 255)  # Светло-синий
                    elif status == 'Error':
                        return QColor(255, 200, 200)  # Светло-красный
                    else:
                        return QColor(240, 240, 240)  # Светло-серый
                
                elif role == Qt.ItemDataRole.FontRole:
                    # Жирный шрифт для активных задач
                    status = item.get('status', 'Unknown')
                    if status == 'Running':
                        font = QFont()
                        font.setBold(True)
                        return font
                
                return None
            
            def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
                if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
                    if section < len(self.headers):
                        return self.headers[section]
                return None
            
            def update_data(self, data_list):
                self.beginResetModel()
                self.data_list = data_list
                self.endResetModel()
        
        self.model = ConfigHistoryTableModel()
        
        # Инициализируем пустые данные
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        self.model.update_data([])
        
        # Настройка фильтров
        self._setup_table_filters()
        
        # Настройка контекстного меню
        self._setup_context_menu()

    def _setup_time_layout(self):
        self._setup_datetime()
        self._setup_buttons()

        self.time_layout = QHBoxLayout()
        self.time_layout.addWidget(self.start_time)
        self.time_layout.addWidget(self.finish_time)
        self.time_layout.addWidget(self.reset_button)
        self.time_layout.addWidget(self.search_button)

    def _setup_datetime(self):
        self.start_time = QDateTimeEdit()
        self.start_time.setMinimumWidth(200)
        self.start_time.setCalendarPopup(True)
        self.start_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.start_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.start_time.setDateTime(self.current_start_time)
        self.start_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.start_time.setKeyboardTracking(False)
        self.start_time.editingFinished.connect(self.start_time_update)

        self.finish_time = QDateTimeEdit()
        self.finish_time.setMinimumWidth(200)
        self.finish_time.setCalendarPopup(True)
        self.finish_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.finish_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.finish_time.setDateTime(self.current_end_time)
        self.finish_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.finish_time.setKeyboardTracking(False)
        self.finish_time.editingFinished.connect(self.finish_time_update)

    def _setup_buttons(self):
        self.reset_button = QPushButton('Reset')
        self.reset_button.setMinimumWidth(200)
        self.reset_button.clicked.connect(self._reset_filter)
        self.search_button = QPushButton('Search')
        self.search_button.setMinimumWidth(200)
        self.search_button.clicked.connect(self._filter_by_time)

    def _setup_config_buttons(self):
        """Настройка кнопок для работы с конфигурациями."""
        self.config_buttons_layout = QHBoxLayout()
        
        # Кнопка восстановления конфигурации
        self.restore_config_button = QPushButton('Восстановить конфигурацию')
        self.restore_config_button.setMinimumWidth(200)
        self.restore_config_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        self.restore_config_button.clicked.connect(self._on_restore_config_clicked)
        self.restore_config_button.setEnabled(False)
        
        # Кнопка сравнения конфигураций
        self.compare_configs_button = QPushButton('Сравнить конфигурации')
        self.compare_configs_button.setMinimumWidth(200)
        self.compare_configs_button.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        self.compare_configs_button.clicked.connect(self._on_compare_configs_clicked)
        self.compare_configs_button.setEnabled(False)
        
        # Кнопка экспорта истории
        self.export_history_button = QPushButton('Экспорт истории')
        self.export_history_button.setMinimumWidth(200)
        self.export_history_button.setStyleSheet("QPushButton { background-color: #FF9800; color: white; }")
        self.export_history_button.clicked.connect(self._on_export_history_clicked)
        
        # Добавляем кнопки в layout
        self.config_buttons_layout.addWidget(self.restore_config_button)
        self.config_buttons_layout.addWidget(self.compare_configs_button)
        self.config_buttons_layout.addWidget(self.export_history_button)
        self.config_buttons_layout.addStretch()
        
        # Подключаем сигнал изменения выбора в таблице
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def showEvent(self, show_event):
        # Загружаем данные только при первом показе окна
        if not self.data_loaded and hasattr(self, 'config_history_manager') and self.config_history_manager:
            self.retrieve_data_signal.emit()
            self.data_loaded = True
        show_event.accept()

    @pyqtSlot()
    def start_time_update(self):
        self.block_updates = True
        if self.start_time.calendarWidget().hasFocus():
            return
        self.start_time_updated = True

    @pyqtSlot()
    def finish_time_update(self):
        self.block_updates = True
        if self.finish_time.calendarWidget().hasFocus():
            return
        self.finish_time_updated = True

    @pyqtSlot()
    def _reset_filter(self):
        if self.block_updates:
            self._retrieve_data()
            self.block_updates = False

    @pyqtSlot()
    def _filter_by_time(self):
        if not self.start_time_updated or not self.finish_time_updated:
            return
        self._filter_records(self.start_time.dateTime().toPyDateTime(), self.finish_time.dateTime().toPyDateTime())

    def _filter_records(self, start_time, finish_time):
        self.current_start_time = start_time
        self.current_end_time = finish_time
        # Загружаем данные через ConfigHistoryManager с новыми временными рамками
        self._load_data()

    def _retrieve_data(self):
        if not self.isVisible():
            return
        
        # Защита от повторных вызовов
        if hasattr(self, '_loading_data') and self._loading_data:
            return
        
        self._loading_data = True
        
        try:
            # Обновляем временные рамки
            self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
            self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
            
            # Сбрасываем дату в фильтрах
            self.start_time.setDateTime(
                QDateTime.fromString(self.current_start_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))
            self.finish_time.setDateTime(
                QDateTime.fromString(self.current_end_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))

            # Загружаем данные через ConfigHistoryManager
            self._load_data()
        finally:
            self._loading_data = False

    @pyqtSlot(QModelIndex)
    def _display_params(self, index):
        col = index.column()
        if col != 4:
            return
        
        # Получаем данные из модели
        row = index.row()
        if hasattr(self.model, 'data_list') and row < len(self.model.data_list):
            item = self.model.data_list[row]
            config_info = item.get('configuration_info', {})
            
            if config_info:
                self.params_win.set_data(config_info)
            else:
                # Показываем сообщение, если конфигурация недоступна
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Информация", "Конфигурация недоступна для этого элемента.")
        else:
            # Показываем сообщение, если данные недоступны
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Информация", "Данные недоступны.")

    def set_config_history_manager(self, config_history_manager: ConfigHistoryManager):
        """
        Установить ConfigHistoryManager для работы с историей конфигураций.
        
        Args:
            config_history_manager: Экземпляр ConfigHistoryManager
        """
        self.config_history_manager = config_history_manager
        # Загружаем данные при установке менеджера только если окно уже показано
        if self.isVisible() and not self.data_loaded:
            self._load_data()
            self.data_loaded = True
    
    def refresh_data(self):
        """Принудительно обновить данные из базы данных"""
        if hasattr(self, 'config_history_manager') and self.config_history_manager:
            self._load_data()
            self.data_loaded = True
    
    def _setup_table_filters(self):
        """Настройка фильтров для таблицы"""
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton
        from PyQt6.QtCore import Qt
        
        # Создаем панель фильтров
        filters_layout = QHBoxLayout()
        
        # Фильтр по статусу
        status_label = QLabel("Статус:")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Все", "Running", "Stopped", "Error", "Unknown"])
        self.status_filter.currentTextChanged.connect(self._on_status_filter_changed)
        
        # Фильтр по проекту
        project_label = QLabel("Проект:")
        self.project_filter = QComboBox()
        self.project_filter.addItem("Все")
        self.project_filter.currentTextChanged.connect(self._on_project_filter_changed)
        
        # Поиск по ID
        search_label = QLabel("Поиск:")
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("Введите Job ID или Config ID...")
        self.search_filter.textChanged.connect(self._apply_filters)
        
        # Кнопка сброса фильтров
        reset_filters_btn = QPushButton("Сбросить фильтры")
        reset_filters_btn.clicked.connect(self._reset_filters)
        
        filters_layout.addWidget(status_label)
        filters_layout.addWidget(self.status_filter)
        filters_layout.addWidget(project_label)
        filters_layout.addWidget(self.project_filter)
        filters_layout.addWidget(search_label)
        filters_layout.addWidget(self.search_filter)
        filters_layout.addWidget(reset_filters_btn)
        filters_layout.addStretch()
        
        # Добавляем панель фильтров в основной layout
        self.main_layout.addLayout(filters_layout)
    
    def _setup_context_menu(self):
        """Настройка контекстного меню для таблицы"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtCore import Qt
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, position):
        """Показать контекстное меню"""
        from PyQt6.QtWidgets import QMenu
        
        if self.table.itemAt(position) is None:
            return
        
        menu = QMenu(self)
        
        # Получаем выбранные строки
        selected_rows = set()
        for index in self.table.selectionModel().selectedRows():
            selected_rows.add(index.row())
        
        if len(selected_rows) == 1:
            # Одна строка выбрана
            row = list(selected_rows)[0]
            job_data = self.model.data_list[row] if row < len(self.model.data_list) else None
            
            if job_data:
                # Детали задачи
                details_action = menu.addAction("Показать детали")
                details_action.triggered.connect(lambda: self._show_job_details(job_data))
                
                menu.addSeparator()
                
                # Восстановить конфигурацию
                restore_action = menu.addAction("Восстановить конфигурацию")
                restore_action.triggered.connect(lambda: self._on_restore_config_clicked())
                
                # Экспорт конфигурации
                export_action = menu.addAction("Экспорт конфигурации")
                export_action.triggered.connect(lambda: self._export_single_config(job_data))
                
        elif len(selected_rows) == 2:
            # Две строки выбраны
            compare_action = menu.addAction("Сравнить конфигурации")
            compare_action.triggered.connect(self._on_compare_configs_clicked)
            
        if len(selected_rows) > 0:
            menu.addSeparator()
            
            # Удалить выбранные записи
            delete_action = menu.addAction("Удалить выбранные")
            delete_action.triggered.connect(self._delete_selected_jobs)
            
            # Экспорт выбранных
            export_selected_action = menu.addAction("Экспорт выбранных")
            export_selected_action.triggered.connect(self._export_selected_configs)
        
        if menu.actions():
            menu.exec(self.table.mapToGlobal(position))
    
    def _apply_filters(self):
        """Применить фильтры к данным"""
        if not self.config_history_manager or self.updating_filters:
            return
        
        self.updating_filters = True
        
        try:
            # Получаем все данные
            all_data = self.config_history_manager.get_config_history(
                start_date=self.current_start_time,
                end_date=self.current_end_time
            )
            
            # Применяем фильтры
            filtered_data = []
            
            for item in all_data:
                # Фильтр по статусу
                status = item.get('status', 'Unknown')
                if self.status_filter.currentText() != "Все" and status != self.status_filter.currentText():
                    continue
                
                # Фильтр по проекту
                project_id = str(item.get('project_id', ''))
                if self.project_filter.currentText() != "Все" and project_id != self.project_filter.currentText():
                    continue
                
                # Поиск по ID
                search_text = self.search_filter.text().lower()
                if search_text:
                    job_id = str(item.get('job_id', '')).lower()
                    config_id = str(item.get('configuration_id', '')).lower()
                    if search_text not in job_id and search_text not in config_id:
                        continue
                
                filtered_data.append(item)
            
            # Обновляем модель
            self.model.update_data(filtered_data)
            
            # Обновляем список проектов в фильтре
            self._update_project_filter(all_data)
        finally:
            self.updating_filters = False
    
    def _reset_filters(self):
        """Сбросить все фильтры"""
        self.status_filter.setCurrentText("Все")
        self.project_filter.setCurrentText("Все")
        self.search_filter.clear()
        self._apply_filters()
    
    def _update_project_filter(self, data):
        """Обновить список проектов в фильтре"""
        projects = set()
        for item in data:
            project_id = str(item.get('project_id', ''))
            if project_id:
                projects.add(project_id)
        
        current_text = self.project_filter.currentText()
        
        # Временно отключаем сигнал, чтобы избежать рекурсии
        try:
            self.project_filter.currentTextChanged.disconnect(self._on_project_filter_changed)
        except TypeError:
            # Сигнал может быть не подключен
            pass
        
        self.project_filter.clear()
        self.project_filter.addItem("Все")
        
        for project in sorted(projects):
            self.project_filter.addItem(project)
        
        # Восстанавливаем выбранный проект
        index = self.project_filter.findText(current_text)
        if index >= 0:
            self.project_filter.setCurrentIndex(index)
        
        # Подключаем сигнал обратно
        self.project_filter.currentTextChanged.connect(self._on_project_filter_changed)
    
    def _show_job_details(self, job_data):
        """Показать детали задачи"""
        dialog = JobDetailsDialog(job_data, self)
        dialog.exec()
    
    def _export_single_config(self, job_data):
        """Экспорт одной конфигурации"""
        if not self.config_history_manager:
            return
        
        config_id = job_data.get('configuration_id')
        if not config_id:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить ID конфигурации")
            return
        
        # Выбираем файл для экспорта
        from PyQt6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Экспорт конфигурации", 
            f"config_{config_id}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            try:
                self.config_history_manager.export_config_history([config_id], filename)
                QMessageBox.information(self, "Успех", f"Конфигурация экспортирована в {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {str(e)}")
    
    def _delete_selected_jobs(self):
        """Удалить выбранные задачи"""
        selected_rows = set()
        for index in self.table.selectionModel().selectedRows():
            selected_rows.add(index.row())
        
        if not selected_rows:
            return
        
        # Подтверждение удаления
        reply = QMessageBox.question(
            self, 
            "Подтверждение удаления", 
            f"Вы уверены, что хотите удалить {len(selected_rows)} записей?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                for row in selected_rows:
                    if row < len(self.model.data_list):
                        job_data = self.model.data_list[row]
                        job_id = job_data.get('job_id')
                        if job_id and self.config_history_manager:
                            self.config_history_manager.delete_job(job_id)
                
                QMessageBox.information(self, "Успех", "Записи успешно удалены")
                self._load_data()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка удаления: {str(e)}")
    
    def _export_selected_configs(self):
        """Экспорт выбранных конфигураций"""
        selected_rows = set()
        for index in self.table.selectionModel().selectedRows():
            selected_rows.add(index.row())
        
        if not selected_rows:
            return
        
        config_ids = []
        for row in selected_rows:
            if row < len(self.model.data_list):
                job_data = self.model.data_list[row]
                config_id = job_data.get('configuration_id')
                if config_id:
                    config_ids.append(config_id)
        
        if not config_ids:
            QMessageBox.warning(self, "Ошибка", "Не удалось получить ID конфигураций")
            return
        
        # Выбираем файл для экспорта
        from PyQt6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, 
            "Экспорт конфигураций", 
            f"configs_export_{len(config_ids)}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            try:
                self.config_history_manager.export_config_history(config_ids, filename)
                QMessageBox.information(self, "Успех", f"Конфигурации экспортированы в {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка экспорта: {str(e)}")
    
    def _load_data(self):
        """Загружает данные из ConfigHistoryManager."""
        if hasattr(self, 'config_history_manager') and self.config_history_manager:
            try:
                # Получаем историю конфигураций
                config_history = self.config_history_manager.get_config_history(
                    start_date=self.current_start_time,
                    end_date=self.current_end_time,
                    limit=100
                )
                
                # Обновляем модель данных
                if hasattr(self.model, 'update_data'):
                    self.model.update_data(config_history)
                
                # Применяем фильтры если они настроены
                if hasattr(self, 'status_filter'):
                    self._apply_filters()
                
            except Exception as e:
                print(f"Error loading data: {e}")
                # В случае ошибки показываем пустую таблицу
                if hasattr(self.model, 'update_data'):
                    self.model.update_data([])

    @pyqtSlot()
    def _on_selection_changed(self):
        """Обработка изменения выбора в таблице."""
        selection = self.table.selectionModel().selectedRows()
        
        # Включаем/выключаем кнопки в зависимости от выбора
        has_selection = len(selection) > 0
        self.restore_config_button.setEnabled(has_selection)
        
        # Для сравнения нужно минимум 2 выбранные строки
        has_multiple_selection = len(selection) >= 2
        self.compare_configs_button.setEnabled(has_multiple_selection)

    @pyqtSlot()
    def _on_restore_config_clicked(self):
        """Обработка нажатия кнопки восстановления конфигурации."""
        if not self.config_history_manager:
            QMessageBox.warning(
                self,
                "Ошибка",
                "ConfigHistoryManager не инициализирован."
            )
            return
        
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Пожалуйста, выберите конфигурацию для восстановления."
            )
            return
        
        # Берем первую выбранную строку
        row = selection[0].row()
        job_id = self.model.data(self.model.index(row, 1))  # Job ID в колонке 1
        
        if not job_id:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось получить Job ID для выбранной конфигурации."
            )
            return
        
        # Получаем информацию о конфигурации
        config_info = self.config_history_manager.get_config_by_job_id(job_id)
        if not config_info:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не удалось получить информацию о конфигурации для Job ID: {job_id}"
            )
            return
        
        # Показываем диалог восстановления
        dialog = ConfigRestoreDialog(config_info, self)
        dialog.config_restored.connect(self._on_config_restored)
        dialog.exec()

    @pyqtSlot()
    def _on_compare_configs_clicked(self):
        """Обработка нажатия кнопки сравнения конфигураций."""
        if not self.config_history_manager:
            QMessageBox.warning(
                self,
                "Ошибка",
                "ConfigHistoryManager не инициализирован."
            )
            return
        
        selection = self.table.selectionModel().selectedRows()
        if len(selection) < 2:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Пожалуйста, выберите минимум 2 конфигурации для сравнения."
            )
            return
        
        # Получаем Job ID для выбранных строк
        job_ids = []
        for selected_row in selection[:2]:  # Берем только первые 2
            row = selected_row.row()
            job_id = self.model.data(self.model.index(row, 1))
            if job_id:
                job_ids.append(job_id)
        
        if len(job_ids) < 2:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось получить Job ID для выбранных конфигураций."
            )
            return
        
        # Получаем историю конфигураций для диалога сравнения
        config_history = self.config_history_manager.get_config_history(limit=100)
        
        # Показываем диалог сравнения
        dialog = ConfigCompareDialog(config_history, self)
        dialog.exec()

    @pyqtSlot()
    def _on_export_history_clicked(self):
        """Обработка нажатия кнопки экспорта истории."""
        if not self.config_history_manager:
            QMessageBox.warning(
                self,
                "Ошибка",
                "ConfigHistoryManager не инициализирован."
            )
            return
        
        # Открываем диалог экспорта с расширенными опциями
        export_dialog = ExportHistoryDialog(self.config_history_manager, self)
        export_dialog.exec()

    @pyqtSlot(dict)
    def _on_config_restored(self, restore_data: dict):
        """Обработка успешного восстановления конфигурации."""
        job_id = restore_data.get('job_id')
        target_path = restore_data.get('target_path')
        backup_path = restore_data.get('backup_path')
        
        message = f"Конфигурация успешно восстановлена!\n\n"
        message += f"Job ID: {job_id}\n"
        message += f"Файл: {target_path}\n"
        
        if backup_path:
            message += f"Резервная копия: {backup_path}\n"
        
        if restore_data.get('restart_pipeline'):
            message += "\n⚠️ Не забудьте перезапустить pipeline для применения изменений."
        
        QMessageBox.information(
            self,
            "Восстановление завершено",
            message
        )

    # Методы управления проектами
    def _refresh_projects_list(self):
        """Обновить список проектов"""
        # Защита от повторных вызовов
        if hasattr(self, '_refreshing_projects') and self._refreshing_projects:
            return
        
        self._refreshing_projects = True
        
        try:
            if not hasattr(self, 'config_history_manager') or not self.config_history_manager:
                return
            
            # Получаем список проектов из базы данных
            projects = self.config_history_manager.get_projects_list()
            
            # Очищаем комбобокс
            self.current_project_combo.clear()
            
            # Добавляем "Все проекты"
            self.current_project_combo.addItem("Все проекты", "all")
            
            # Добавляем проекты
            for project in projects:
                project_id = project.get('project_id', 'unknown')
                project_name = project.get('project_name', f'Project {project_id}')
                self.current_project_combo.addItem(project_name, project_id)
            
            # Обновляем статистику
            self._update_project_statistics()
            
        except Exception as e:
            print(f"Error refreshing projects list: {e}")
            # Не показываем QMessageBox, чтобы избежать проблем с GUI
        finally:
            self._refreshing_projects = False

    def _on_current_project_changed(self, project_name):
        """Обработка изменения текущего проекта"""
        if project_name == "Все проекты":
            self.current_project_id = None
        else:
            # Получаем project_id из данных комбобокса
            current_index = self.current_project_combo.currentIndex()
            self.current_project_id = self.current_project_combo.itemData(current_index)
        
        # Обновляем статистику
        self._update_project_statistics()
        
        # Применяем фильтры
        self._apply_filters()

    def _create_new_project(self):
        """Создать новый проект"""
        from PyQt6.QtWidgets import QInputDialog, QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox
        from PyQt6.QtWidgets import QLineEdit, QTextEdit
        
        # Создаем диалог для ввода данных проекта
        dialog = QDialog(self)
        dialog.setWindowTitle("Создать новый проект")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Форма для ввода данных
        form_layout = QFormLayout()
        
        # Название проекта
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Введите название проекта")
        form_layout.addRow("Название проекта:", name_edit)
        
        # Описание проекта
        description_edit = QTextEdit()
        description_edit.setPlaceholderText("Введите описание проекта (необязательно)")
        description_edit.setMaximumHeight(100)
        form_layout.addRow("Описание:", description_edit)
        
        layout.addLayout(form_layout)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            project_name = name_edit.text().strip()
            project_description = description_edit.toPlainText().strip()
            
            if not project_name:
                QMessageBox.warning(self, "Ошибка", "Название проекта не может быть пустым")
                return
            
            try:
                if self.config_history_manager:
                    result = self.config_history_manager.create_project(project_name, project_description)
                    if result.get('success'):
                        QMessageBox.information(self, "Успех", f"Проект '{project_name}' успешно создан")
                        self._refresh_projects_list()
                    else:
                        QMessageBox.critical(self, "Ошибка", f"Не удалось создать проект: {result.get('error', 'Неизвестная ошибка')}")
                else:
                    QMessageBox.warning(self, "Ошибка", "ConfigHistoryManager не инициализирован")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка при создании проекта: {str(e)}")

    def _edit_current_project(self):
        """Редактировать текущий проект"""
        current_index = self.current_project_combo.currentIndex()
        if current_index <= 0:  # "Все проекты" или пустой список
            QMessageBox.warning(self, "Ошибка", "Выберите проект для редактирования")
            return
        
        project_id = self.current_project_combo.itemData(current_index)
        project_name = self.current_project_combo.currentText()
        
        from PyQt6.QtWidgets import QInputDialog, QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox
        from PyQt6.QtWidgets import QLineEdit, QTextEdit
        
        # Создаем диалог для редактирования
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Редактировать проект: {project_name}")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Форма для редактирования
        form_layout = QFormLayout()
        
        # Название проекта
        name_edit = QLineEdit(project_name)
        form_layout.addRow("Название проекта:", name_edit)
        
        # Описание проекта (получаем из БД)
        description_edit = QTextEdit()
        description_edit.setMaximumHeight(100)
        form_layout.addRow("Описание:", description_edit)
        
        # Загружаем описание из БД
        try:
            if self.config_history_manager:
                project_info = self.config_history_manager.get_project_info(project_id)
                if project_info:
                    description_edit.setPlainText(project_info.get('project_description', ''))
        except Exception as e:
            print(f"Ошибка загрузки описания проекта: {e}")
        
        layout.addLayout(form_layout)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_edit.text().strip()
            new_description = description_edit.toPlainText().strip()
            
            if not new_name:
                QMessageBox.warning(self, "Ошибка", "Название проекта не может быть пустым")
                return
            
            try:
                if self.config_history_manager:
                    result = self.config_history_manager.update_project(project_id, new_name, new_description)
                    if result.get('success'):
                        QMessageBox.information(self, "Успех", f"Проект успешно обновлен")
                        self._refresh_projects_list()
                    else:
                        QMessageBox.critical(self, "Ошибка", f"Не удалось обновить проект: {result.get('error', 'Неизвестная ошибка')}")
                else:
                    QMessageBox.warning(self, "Ошибка", "ConfigHistoryManager не инициализирован")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка при обновлении проекта: {str(e)}")

    def _delete_current_project(self):
        """Удалить текущий проект"""
        current_index = self.current_project_combo.currentIndex()
        if current_index <= 0:  # "Все проекты" или пустой список
            QMessageBox.warning(self, "Ошибка", "Выберите проект для удаления")
            return
        
        project_id = self.current_project_combo.itemData(current_index)
        project_name = self.current_project_combo.currentText()
        
        # Подтверждение удаления
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            f"Вы уверены, что хотите удалить проект '{project_name}'?\n\n"
            f"Это действие нельзя отменить. Все связанные задачи будут помечены как 'без проекта'.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.config_history_manager:
                    result = self.config_history_manager.delete_project(project_id)
                    if result.get('success'):
                        QMessageBox.information(self, "Успех", f"Проект '{project_name}' успешно удален")
                        self._refresh_projects_list()
                    else:
                        QMessageBox.critical(self, "Ошибка", f"Не удалось удалить проект: {result.get('error', 'Неизвестная ошибка')}")
                else:
                    QMessageBox.warning(self, "Ошибка", "ConfigHistoryManager не инициализирован")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка при удалении проекта: {str(e)}")

    def _update_project_statistics(self):
        """Обновить статистику проекта"""
        # Защита от повторных вызовов
        if hasattr(self, '_updating_stats') and self._updating_stats:
            return
        
        self._updating_stats = True
        
        try:
            if not self.current_project_id or not hasattr(self, 'config_history_manager') or not self.config_history_manager:
                if hasattr(self, 'project_stats_label'):
                    self.project_stats_label.setText("Статистика проекта не загружена")
                return
            
            # Получаем статистику проекта
            stats = self.config_history_manager.get_project_statistics(self.current_project_id)
            
            if stats and hasattr(self, 'project_stats_label'):
                total_jobs = stats.get('total_jobs', 0)
                running_jobs = stats.get('running_jobs', 0)
                completed_jobs = stats.get('completed_jobs', 0)
                error_jobs = stats.get('error_jobs', 0)
                total_duration = stats.get('total_duration', 0)
                
                stats_text = f"Задач: {total_jobs} | Запущено: {running_jobs} | Завершено: {completed_jobs} | Ошибок: {error_jobs}"
                if total_duration > 0:
                    stats_text += f" | Общее время: {total_duration:.1f}ч"
                
                self.project_stats_label.setText(stats_text)
            else:
                if hasattr(self, 'project_stats_label'):
                    self.project_stats_label.setText("Статистика недоступна")
                
        except Exception as e:
            print(f"Error updating project statistics: {e}")
            if hasattr(self, 'project_stats_label'):
                self.project_stats_label.setText(f"Ошибка загрузки статистики: {str(e)}")
        finally:
            self._updating_stats = False

    def _show_project_statistics(self):
        """Показать детальную статистику проекта"""
        if not self.current_project_id:
            QMessageBox.warning(self, "Ошибка", "Выберите проект для просмотра статистики")
            return
        
        try:
            if not self.config_history_manager:
                QMessageBox.warning(self, "Ошибка", "ConfigHistoryManager не инициализирован")
                return
            
            # Получаем детальную статистику
            stats = self.config_history_manager.get_project_statistics(self.current_project_id, detailed=True)
            
            if not stats:
                QMessageBox.information(self, "Статистика", "Статистика для выбранного проекта недоступна")
                return
            
            # Создаем диалог со статистикой
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Статистика проекта: {self.current_project_combo.currentText()}")
            dialog.setModal(True)
            dialog.resize(500, 400)
            
            layout = QVBoxLayout(dialog)
            
            # Текстовое поле со статистикой
            stats_text = QTextEdit()
            stats_text.setReadOnly(True)
            
            # Форматируем статистику
            stats_content = f"""Детальная статистика проекта: {self.current_project_combo.currentText()}

Общая информация:
• Всего задач: {stats.get('total_jobs', 0)}
• Запущенных задач: {stats.get('running_jobs', 0)}
• Завершенных задач: {stats.get('completed_jobs', 0)}
• Задач с ошибками: {stats.get('error_jobs', 0)}

Временные характеристики:
• Общее время выполнения: {stats.get('total_duration', 0):.2f} часов
• Среднее время выполнения: {stats.get('avg_duration', 0):.2f} часов
• Самая быстрая задача: {stats.get('min_duration', 0):.2f} часов
• Самая медленная задача: {stats.get('max_duration', 0):.2f} часов

Производительность:
• Всего обработано кадров: {stats.get('total_frames', 0):,}
• Всего обнаружено объектов: {stats.get('total_objects', 0):,}
• Всего событий: {stats.get('total_events', 0):,}
• Средний FPS: {stats.get('avg_fps', 0):.2f}

Период активности:
• Первая задача: {stats.get('first_job_date', 'Неизвестно')}
• Последняя задача: {stats.get('last_job_date', 'Неизвестно')}
• Период активности: {stats.get('activity_period', 'Неизвестно')}
"""
            
            stats_text.setPlainText(stats_content)
            layout.addWidget(stats_text)
            
            # Кнопка закрытия
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            button_box.accepted.connect(dialog.accept)
            layout.addWidget(button_box)
            
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при получении статистики: {str(e)}")
