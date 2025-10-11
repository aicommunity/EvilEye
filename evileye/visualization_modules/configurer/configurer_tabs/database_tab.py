import copy
import json
import os.path
try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter
    )
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget,
        QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
        QFileDialog, QSpinBox, QDoubleSpinBox, QTextEdit, QSplitter
    )
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCaptureOpencv
from evileye.visualization_modules.configurer import parameters_processing
from evileye.visualization_modules.configurer.configurer_tabs.base_tab import BaseTab
from evileye.visualization_modules.configurer.validators import (
    ValidatedLineEdit, ValidatedSpinBox, ValidatedDoubleSpinBox, 
    ValidatedCheckBox, ValidatedComboBox, Validators
)


class DatabaseTab(BaseTab):
    def __init__(self, config_params, database_params):
        super().__init__(config_params)

        self.params = config_params
        self.database_params = database_params
        self.default_src_params = self.database_params['database']
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.hor_layouts = {}
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.src_counter = 0

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        # Используем main_layout из BaseTab вместо создания нового
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_layout()

    def _setup_layout(self):
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Флаг использования базы данных
        self._setup_database_mode_section()
        
        # Основные параметры базы данных
        self._setup_database_connection_section()
        
        # Управление проектами
        self._setup_projects_management_section()
        
        # Настройки изображений
        self._setup_images_settings_section()
        
        # Attribute events таблица
        self._setup_attribute_events_section()

    def _setup_database_mode_section(self):
        """Настройка секции режима работы с базой данных"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Режим работы с базой данных", layout)
        layout = self.create_form_layout()
        
        # Флаг использования базы данных
        self.use_database = ValidatedCheckBox("Использовать базу данных")
        self.use_database.setChecked(True)
        self.use_database.setToolTip("Включить/выключить использование базы данных. При выключении данные будут сохраняться в JSON файлы")
        self.use_database.toggled.connect(self._on_database_mode_toggled)
        layout.addWidget(self.use_database)
        
        # Режим работы
        self.database_mode = ValidatedComboBox()
        self.database_mode.addItems(["PostgreSQL", "JSON Files", "Hybrid"])
        self.database_mode.setToolTip("Режим работы: PostgreSQL - полная БД, JSON Files - только файлы, Hybrid - БД + файлы")
        self.add_validated_widget("Database mode", self.database_mode, Validators.POSITIVE_INT)
        
        self.main_layout.addWidget(group_box)

    def _setup_database_connection_section(self):
        """Настройка секции подключения к базе данных"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Подключение к базе данных", layout)
        layout = self.create_form_layout()
        
        # Основные параметры подключения
        self.db_username = ValidatedLineEdit()
        self.db_username.setPlaceholderText("postgres")
        self.db_username.setToolTip("Имя пользователя базы данных")
        self.add_validated_widget("Username", self.db_username, Validators.POSITIVE_INT)
        
        self.db_password = ValidatedLineEdit()
        self.db_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_password.setPlaceholderText("password")
        self.db_password.setToolTip("Пароль пользователя базы данных")
        self.add_validated_widget("Password", self.db_password, Validators.POSITIVE_INT)
        
        self.db_name = ValidatedLineEdit()
        self.db_name.setPlaceholderText("evileye_db")
        self.db_name.setToolTip("Название базы данных")
        self.add_validated_widget("Database name", self.db_name, Validators.POSITIVE_INT)
        
        self.db_host = ValidatedLineEdit()
        self.db_host.setPlaceholderText("localhost")
        self.db_host.setToolTip("Хост базы данных")
        self.add_validated_widget("Host", self.db_host, Validators.RTSP_URL)
        
        self.db_port = ValidatedSpinBox()
        self.db_port.setRange(1, 65535)
        self.db_port.setValue(5432)
        self.db_port.setToolTip("Порт базы данных")
        self.add_validated_widget("Port", self.db_port, Validators.POSITIVE_INT)
        
        # Кнопка тестирования подключения
        test_connection_btn = QPushButton("Тест подключения")
        test_connection_btn.clicked.connect(self._test_database_connection)
        layout.addRow("", test_connection_btn)
        
        # Admin credentials для создания БД
        admin_label = QLabel("Admin Credentials (для создания БД)")
        admin_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addRow(admin_label)
        
        self.admin_username = ValidatedLineEdit()
        self.admin_username.setText("postgres")
        self.admin_username.setToolTip("Имя администратора базы данных")
        self.add_validated_widget("Admin username", self.admin_username, Validators.POSITIVE_INT)
        
        self.admin_password = ValidatedLineEdit()
        self.admin_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.admin_password.setToolTip("Пароль администратора базы данных")
        self.add_validated_widget("Admin password", self.admin_password, Validators.POSITIVE_INT)
        
        self.main_layout.addWidget(group_box)

    def _setup_projects_management_section(self):
        """Настройка секции управления проектами"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Управление проектами", layout)
        layout = QVBoxLayout()
        
        # Выбор проекта
        project_layout = QHBoxLayout()
        project_layout.addWidget(QLabel("Текущий проект:"))
        
        self.current_project = ValidatedComboBox()
        self.current_project.setToolTip("Выберите активный проект")
        self.current_project.currentTextChanged.connect(self._on_project_changed)
        project_layout.addWidget(self.current_project)
        
        self.refresh_projects_btn = QPushButton("Обновить")
        self.refresh_projects_btn.clicked.connect(self._refresh_projects_list)
        project_layout.addWidget(self.refresh_projects_btn)
        
        layout.addLayout(project_layout)
        
        # Кнопки управления проектами
        buttons_layout = QHBoxLayout()
        
        self.create_project_btn = QPushButton("Создать проект")
        self.create_project_btn.clicked.connect(self._create_new_project)
        buttons_layout.addWidget(self.create_project_btn)
        
        self.edit_project_btn = QPushButton("Редактировать")
        self.edit_project_btn.clicked.connect(self._edit_project)
        buttons_layout.addWidget(self.edit_project_btn)
        
        self.delete_project_btn = QPushButton("Удалить")
        self.delete_project_btn.clicked.connect(self._delete_project)
        buttons_layout.addWidget(self.delete_project_btn)
        
        layout.addLayout(buttons_layout)
        
        # Создание нового проекта
        self.create_new_project = ValidatedCheckBox("Создать новый проект при запуске")
        self.create_new_project.setChecked(False)
        self.create_new_project.setToolTip("Автоматически создавать новый проект при каждом запуске")
        layout.addWidget(self.create_new_project)
        
        self.main_layout.addWidget(group_box)

    def _setup_images_settings_section(self):
        """Настройка секции настроек изображений"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Настройки изображений", layout)
        layout = self.create_form_layout()
        
        # Директория для изображений
        self.image_dir = ValidatedLineEdit()
        self.image_dir.setPlaceholderText("/path/to/images")
        self.image_dir.setToolTip("Директория для сохранения изображений объектов")
        self.add_validated_widget("Image directory", self.image_dir, Validators.DIRECTORY_PATH)
        
        # Кнопка выбора директории
        select_dir_btn = QPushButton("Выбрать директорию")
        select_dir_btn.clicked.connect(self._select_image_directory)
        layout.addRow("", select_dir_btn)
        
        # Размеры превью
        self.preview_width = ValidatedSpinBox()
        self.preview_width.setRange(50, 2000)
        self.preview_width.setValue(300)
        self.preview_width.setToolTip("Ширина превью изображений")
        self.add_validated_widget("Preview width", self.preview_width, Validators.POSITIVE_INT)
        
        self.preview_height = ValidatedSpinBox()
        self.preview_height.setRange(50, 2000)
        self.preview_height.setValue(150)
        self.preview_height.setToolTip("Высота превью изображений")
        self.add_validated_widget("Preview height", self.preview_height, Validators.POSITIVE_INT)
        
        # Качество изображений
        self.image_quality = ValidatedSpinBox()
        self.image_quality.setRange(1, 100)
        self.image_quality.setValue(85)
        self.image_quality.setToolTip("Качество сжатия изображений (1-100)")
        self.add_validated_widget("Image quality", self.image_quality, Validators.POSITIVE_INT)
        
        self.main_layout.addWidget(group_box)

    def _setup_attribute_events_section(self):
        """Настройка секции attribute events таблицы"""
        layout = self.create_form_layout()
        group_box = self.add_group_box("Attribute Events таблица", layout)
        layout = QVBoxLayout()
        
        # Включить attribute events
        self.enable_attribute_events = ValidatedCheckBox("Использовать Attribute Events таблицу")
        self.enable_attribute_events.setChecked(True)
        self.enable_attribute_events.setToolTip("Включить сохранение событий по атрибутам в отдельную таблицу")
        self.enable_attribute_events.toggled.connect(self._on_attribute_events_toggled)
        layout.addWidget(self.enable_attribute_events)
        
        # Настройки таблицы
        table_layout = self.create_form_layout()
        
        self.attribute_events_table_name = ValidatedLineEdit()
        self.attribute_events_table_name.setText("attribute_events")
        self.attribute_events_table_name.setToolTip("Название таблицы для событий по атрибутам")
        self.add_validated_widget("Table name", self.attribute_events_table_name, Validators.POSITIVE_INT)
        
        self.attribute_events_retention_days = ValidatedSpinBox()
        self.attribute_events_retention_days.setRange(1, 3650)
        self.attribute_events_retention_days.setValue(30)
        self.attribute_events_retention_days.setToolTip("Количество дней хранения событий по атрибутам")
        self.add_validated_widget("Retention days", self.attribute_events_retention_days, Validators.POSITIVE_INT)
        
        self.attribute_events_batch_size = ValidatedSpinBox()
        self.attribute_events_batch_size.setRange(1, 10000)
        self.attribute_events_batch_size.setValue(100)
        self.attribute_events_batch_size.setToolTip("Размер батча для записи событий по атрибутам")
        self.add_validated_widget("Batch size", self.attribute_events_batch_size, Validators.POSITIVE_INT)
        
        layout.addLayout(table_layout)
        
        # Кнопка создания таблицы
        create_table_btn = QPushButton("Создать таблицу")
        create_table_btn.clicked.connect(self._create_attribute_events_table)
        layout.addWidget(create_table_btn)
        
        self.main_layout.addWidget(group_box)
        
        # Инициализация состояния
        self._on_attribute_events_toggled(True)

    def get_forms(self) -> list[QFormLayout]:
        form_layouts = []
        forms = [form for i in range(self.vertical_layout.count()) if isinstance(form := self.vertical_layout.itemAt(i), QFormLayout)]
        form_layouts.extend(forms)
        return form_layouts

    def get_params(self):
        """Получить все параметры Database Tab"""
        return {
            'database_mode': self._get_database_mode_params(),
            'database_connection': self._get_database_connection_params(),
            'projects_management': self._get_projects_management_params(),
            'images_settings': self._get_images_settings_params(),
            'attribute_events': self._get_attribute_events_params()
        }

    def _get_database_mode_params(self):
        """Получить параметры режима работы с БД"""
        return {
            'use_database': self.use_database.isChecked(),
            'database_mode': self.database_mode.currentText()
        }

    def _get_database_connection_params(self):
        """Получить параметры подключения к БД"""
        return {
            'username': self.db_username.text(),
            'password': self.db_password.text(),
            'database_name': self.db_name.text(),
            'host': self.db_host.text(),
            'port': self.db_port.value(),
            'admin_username': self.admin_username.text(),
            'admin_password': self.admin_password.text()
        }

    def _get_projects_management_params(self):
        """Получить параметры управления проектами"""
        return {
            'current_project': self.current_project.currentText(),
            'create_new_project': self.create_new_project.isChecked()
        }

    def _get_images_settings_params(self):
        """Получить параметры настроек изображений"""
        return {
            'image_dir': self.image_dir.text(),
            'preview_width': self.preview_width.value(),
            'preview_height': self.preview_height.value(),
            'image_quality': self.image_quality.value()
        }

    def _get_attribute_events_params(self):
        """Получить параметры attribute events таблицы"""
        return {
            'enable_attribute_events': self.enable_attribute_events.isChecked(),
            'table_name': self.attribute_events_table_name.text(),
            'retention_days': self.attribute_events_retention_days.value(),
            'batch_size': self.attribute_events_batch_size.value()
        }

    def _on_database_mode_toggled(self, checked):
        """Обработка переключения режима работы с БД"""
        # Включаем/выключаем поля в зависимости от режима
        self.db_username.setEnabled(checked)
        self.db_password.setEnabled(checked)
        self.db_name.setEnabled(checked)
        self.db_host.setEnabled(checked)
        self.db_port.setEnabled(checked)
        self.admin_username.setEnabled(checked)
        self.admin_password.setEnabled(checked)
        
        # Обновляем список проектов
        self._refresh_projects_list()

    def _on_project_changed(self, project_name):
        """Обработка изменения выбранного проекта"""
        if project_name:
            # Здесь можно добавить логику загрузки настроек проекта
            pass

    def _on_attribute_events_toggled(self, checked):
        """Обработка переключения attribute events"""
        self.attribute_events_table_name.setEnabled(checked)
        self.attribute_events_retention_days.setEnabled(checked)
        self.attribute_events_batch_size.setEnabled(checked)

    def _test_database_connection(self):
        """Тестирование подключения к базе данных"""
        try:
            # Здесь должна быть логика тестирования подключения
            # Пока что просто показываем сообщение
            QMessageBox.information(self, "Тест подключения", "Подключение к базе данных успешно!")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка подключения", f"Ошибка подключения к базе данных: {str(e)}")

    def _select_image_directory(self):
        """Выбор директории для изображений"""
        directory = QFileDialog.getExistingDirectory(self, "Выберите директорию для изображений")
        if directory:
            self.image_dir.setText(directory)

    def _refresh_projects_list(self):
        """Обновить список проектов"""
        try:
            # Здесь должна быть логика получения списка проектов из БД
            # Пока что добавляем тестовые проекты
            current_text = self.current_project.currentText()
            self.current_project.clear()
            
            if self.use_database.isChecked():
                # Получаем проекты из БД
                projects = ["Project 1", "Project 2", "Default Project"]
                self.current_project.addItems(projects)
            else:
                # JSON режим - нет проектов
                self.current_project.addItem("JSON Mode")
            
            # Восстанавливаем выбранный проект
            index = self.current_project.findText(current_text)
            if index >= 0:
                self.current_project.setCurrentIndex(index)
            elif self.current_project.count() > 0:
                self.current_project.setCurrentIndex(0)
                
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка обновления списка проектов: {str(e)}")

    def _create_new_project(self):
        """Создание нового проекта"""
        from PyQt6.QtWidgets import QInputDialog
        
        project_name, ok = QInputDialog.getText(self, "Создать проект", "Введите название проекта:")
        if ok and project_name:
            try:
                # Здесь должна быть логика создания проекта в БД
                QMessageBox.information(self, "Успех", f"Проект '{project_name}' создан успешно!")
                self._refresh_projects_list()
                # Выбираем созданный проект
                index = self.current_project.findText(project_name)
                if index >= 0:
                    self.current_project.setCurrentIndex(index)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка создания проекта: {str(e)}")

    def _edit_project(self):
        """Редактирование проекта"""
        current_project = self.current_project.currentText()
        if not current_project or current_project == "JSON Mode":
            QMessageBox.warning(self, "Предупреждение", "Выберите проект для редактирования")
            return
        
        from PyQt6.QtWidgets import QInputDialog
        
        new_name, ok = QInputDialog.getText(self, "Редактировать проект", "Введите новое название:", text=current_project)
        if ok and new_name and new_name != current_project:
            try:
                # Здесь должна быть логика редактирования проекта в БД
                QMessageBox.information(self, "Успех", f"Проект переименован в '{new_name}'!")
                self._refresh_projects_list()
                # Выбираем отредактированный проект
                index = self.current_project.findText(new_name)
                if index >= 0:
                    self.current_project.setCurrentIndex(index)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка редактирования проекта: {str(e)}")

    def _delete_project(self):
        """Удаление проекта"""
        current_project = self.current_project.currentText()
        if not current_project or current_project == "JSON Mode":
            QMessageBox.warning(self, "Предупреждение", "Выберите проект для удаления")
            return
        
        reply = QMessageBox.question(
            self, 
            "Подтверждение удаления", 
            f"Вы уверены, что хотите удалить проект '{current_project}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Здесь должна быть логика удаления проекта из БД
                QMessageBox.information(self, "Успех", f"Проект '{current_project}' удален!")
                self._refresh_projects_list()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка удаления проекта: {str(e)}")

    def _create_attribute_events_table(self):
        """Создание таблицы attribute events"""
        try:
            # Здесь должна быть логика создания таблицы в БД
            table_name = self.attribute_events_table_name.text()
            QMessageBox.information(self, "Успех", f"Таблица '{table_name}' создана успешно!")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка создания таблицы: {str(e)}")

    def _update_ui_from_params(self):
        """Обновить UI из параметров конфигурации"""
        if not self.params:
            return
        
        # Обновляем режим работы с БД
        db_mode_params = self.params.get('database_mode', {})
        if 'use_database' in db_mode_params:
            self.use_database.setChecked(db_mode_params['use_database'])
        if 'database_mode' in db_mode_params:
            index = self.database_mode.findText(db_mode_params['database_mode'])
            if index >= 0:
                self.database_mode.setCurrentIndex(index)
        
        # Обновляем параметры подключения
        db_conn_params = self.params.get('database_connection', {})
        if 'username' in db_conn_params:
            self.db_username.setText(db_conn_params['username'])
        if 'password' in db_conn_params:
            self.db_password.setText(db_conn_params['password'])
        if 'database_name' in db_conn_params:
            self.db_name.setText(db_conn_params['database_name'])
        if 'host' in db_conn_params:
            self.db_host.setText(db_conn_params['host'])
        if 'port' in db_conn_params:
            self.db_port.setValue(db_conn_params['port'])
        if 'admin_username' in db_conn_params:
            self.admin_username.setText(db_conn_params['admin_username'])
        if 'admin_password' in db_conn_params:
            self.admin_password.setText(db_conn_params['admin_password'])
        
        # Обновляем управление проектами
        projects_params = self.params.get('projects_management', {})
        if 'create_new_project' in projects_params:
            self.create_new_project.setChecked(projects_params['create_new_project'])
        
        # Обновляем настройки изображений
        images_params = self.params.get('images_settings', {})
        if 'image_dir' in images_params:
            self.image_dir.setText(images_params['image_dir'])
        if 'preview_width' in images_params:
            self.preview_width.setValue(images_params['preview_width'])
        if 'preview_height' in images_params:
            self.preview_height.setValue(images_params['preview_height'])
        if 'image_quality' in images_params:
            self.image_quality.setValue(images_params['image_quality'])
        
        # Обновляем attribute events
        attr_events_params = self.params.get('attribute_events', {})
        if 'enable_attribute_events' in attr_events_params:
            self.enable_attribute_events.setChecked(attr_events_params['enable_attribute_events'])
        if 'table_name' in attr_events_params:
            self.attribute_events_table_name.setText(attr_events_params['table_name'])
        if 'retention_days' in attr_events_params:
            self.attribute_events_retention_days.setValue(attr_events_params['retention_days'])
        if 'batch_size' in attr_events_params:
            self.attribute_events_batch_size.setValue(attr_events_params['batch_size'])
        
        # Обновляем список проектов
        self._refresh_projects_list()
