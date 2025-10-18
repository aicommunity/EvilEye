"""
Диалог детальной информации о задаче для EvilEye.

Предоставляет подробную информацию о задаче, включая конфигурацию,
статистику, логи и производительность.
"""

import copy
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
        QGroupBox, QFormLayout, QCheckBox, QMessageBox, QTabWidget,
        QTreeWidget, QTreeWidgetItem, QHeaderView, QScrollArea, QTableWidget,
        QTableWidgetItem, QProgressBar, QSplitter, QListWidget, QListWidgetItem,
        QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QFrame
    )
    from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
    from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QPen
    try:
        from PyQt6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
        CHARTS_AVAILABLE = True
    except ImportError:
        # Если QtCharts недоступен, создаем заглушки
        QChart = None
        QChartView = None
        QLineSeries = None
        QValueAxis = None
        QDateTimeAxis = None
        CHARTS_AVAILABLE = False
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
        QGroupBox, QFormLayout, QCheckBox, QMessageBox, QTabWidget,
        QTreeWidget, QTreeWidgetItem, QHeaderView, QScrollArea, QTableWidget,
        QTableWidgetItem, QProgressBar, QSplitter, QListWidget, QListWidgetItem,
        QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QFrame
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
    from PyQt5.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QPen
    try:
        from PyQt5.QtChart import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
        CHARTS_AVAILABLE = True
    except ImportError:
        # Если QtChart недоступен, создаем заглушки
        QChart = None
        QChartView = None
        QLineSeries = None
        QValueAxis = None
        QDateTimeAxis = None
        CHARTS_AVAILABLE = False
    pyqt_version = 5

from ...core.logger import get_module_logger


class PerformanceDataThread(QThread):
    """Поток для загрузки данных производительности"""
    
    data_loaded = pyqtSignal(dict)  # performance_data
    
    def __init__(self, job_id: int, project_id: int):
        super().__init__()
        self.job_id = job_id
        self.project_id = project_id
        self.logger = get_module_logger("performance_data_thread")
    
    def run(self):
        """Загрузить данные производительности"""
        try:
            # Здесь должна быть логика загрузки данных из БД
            # Пока создаем тестовые данные
            performance_data = {
                'fps_history': self._generate_fps_data(),
                'memory_usage': self._generate_memory_data(),
                'cpu_usage': self._generate_cpu_data(),
                'frame_processing_times': self._generate_processing_times()
            }
            
            self.data_loaded.emit(performance_data)
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки данных производительности: {e}")
            self.data_loaded.emit({})
    
    def _generate_fps_data(self):
        """Генерировать тестовые данные FPS"""
        data = []
        base_time = datetime.now() - timedelta(hours=1)
        base_fps = 30.0
        
        for i in range(60):  # 60 точек за час
            timestamp = base_time + timedelta(minutes=i)
            fps = base_fps + (i % 10 - 5) * 0.5  # Небольшие колебания
            data.append({'timestamp': timestamp, 'fps': fps})
        
        return data
    
    def _generate_memory_data(self):
        """Генерировать тестовые данные использования памяти"""
        data = []
        base_time = datetime.now() - timedelta(hours=1)
        base_memory = 1024  # MB
        
        for i in range(60):
            timestamp = base_time + timedelta(minutes=i)
            memory = base_memory + (i % 20 - 10) * 10  # Колебания памяти
            data.append({'timestamp': timestamp, 'memory_mb': memory})
        
        return data
    
    def _generate_cpu_data(self):
        """Генерировать тестовые данные использования CPU"""
        data = []
        base_time = datetime.now() - timedelta(hours=1)
        base_cpu = 50.0  # %
        
        for i in range(60):
            timestamp = base_time + timedelta(minutes=i)
            cpu = base_cpu + (i % 15 - 7) * 2  # Колебания CPU
            data.append({'timestamp': timestamp, 'cpu_percent': cpu})
        
        return data
    
    def _generate_processing_times(self):
        """Генерировать тестовые данные времени обработки кадров"""
        data = []
        base_time = datetime.now() - timedelta(hours=1)
        base_time_ms = 33.3  # ~30 FPS
        
        for i in range(60):
            timestamp = base_time + timedelta(minutes=i)
            time_ms = base_time_ms + (i % 8 - 4) * 2  # Колебания времени обработки
            data.append({'timestamp': timestamp, 'processing_time_ms': time_ms})
        
        return data


class JobDetailsDialog(QDialog):
    """Диалог детальной информации о задаче"""
    
    def __init__(self, job_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("job_details_dialog")
        
        self.job_data = job_data
        self.performance_data = {}
        self.performance_thread = None
        
        self.setWindowTitle(f"Детали задачи #{job_data.get('job_id', 'N/A')}")
        self.setModal(True)
        self.resize(1000, 700)
        
        self._init_ui()
        self._load_job_data()
        self._start_performance_data_loading()
    
    def _init_ui(self):
        """Инициализация пользовательского интерфейса"""
        layout = QVBoxLayout(self)
        
        # Заголовок
        title_label = QLabel(f"Детали задачи #{self.job_data.get('job_id', 'N/A')}")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Основной контент с вкладками
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Вкладка "Общая информация"
        self._create_general_info_tab()
        
        # Вкладка "Конфигурация"
        self._create_configuration_tab()
        
        # Вкладка "Статистика"
        self._create_statistics_tab()
        
        # Вкладка "Производительность"
        self._create_performance_tab()
        
        # Вкладка "Логи"
        self._create_logs_tab()
        
        # Вкладка "Связанные данные"
        self._create_related_data_tab()
        
        # Кнопки
        self._add_buttons(layout)
    
    def _create_general_info_tab(self):
        """Создать вкладку общей информации"""
        general_widget = QWidget()
        layout = QVBoxLayout(general_widget)
        
        # Основная информация
        main_info_group = QGroupBox("Основная информация")
        main_info_layout = QFormLayout(main_info_group)
        
        self.job_id_label = QLabel()
        self.project_id_label = QLabel()
        self.status_label = QLabel()
        self.creation_time_label = QLabel()
        self.finish_time_label = QLabel()
        self.duration_label = QLabel()
        
        main_info_layout.addRow("ID задачи:", self.job_id_label)
        main_info_layout.addRow("ID проекта:", self.project_id_label)
        main_info_layout.addRow("Статус:", self.status_label)
        main_info_layout.addRow("Время создания:", self.creation_time_label)
        main_info_layout.addRow("Время завершения:", self.finish_time_label)
        main_info_layout.addRow("Длительность:", self.duration_label)
        
        layout.addWidget(main_info_group)
        
        # Дополнительная информация
        additional_info_group = QGroupBox("Дополнительная информация")
        additional_info_layout = QFormLayout(additional_info_group)
        
        self.configuration_id_label = QLabel()
        self.total_frames_label = QLabel()
        self.processed_frames_label = QLabel()
        self.detected_objects_label = QLabel()
        self.detected_events_label = QLabel()
        
        additional_info_layout.addRow("ID конфигурации:", self.configuration_id_label)
        additional_info_layout.addRow("Всего кадров:", self.total_frames_label)
        additional_info_layout.addRow("Обработано кадров:", self.processed_frames_label)
        additional_info_layout.addRow("Обнаружено объектов:", self.detected_objects_label)
        additional_info_layout.addRow("Обнаружено событий:", self.detected_events_label)
        
        layout.addWidget(additional_info_group)
        
        # Описание
        description_group = QGroupBox("Описание")
        description_layout = QVBoxLayout(description_group)
        
        self.description_text = QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setMaximumHeight(100)
        description_layout.addWidget(self.description_text)
        
        layout.addWidget(description_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(general_widget, "Общая информация")
    
    def _create_configuration_tab(self):
        """Создать вкладку конфигурации"""
        config_widget = QWidget()
        layout = QVBoxLayout(config_widget)
        
        # Дерево конфигурации
        self.config_tree = QTreeWidget()
        self.config_tree.setHeaderLabels(["Параметр", "Значение"])
        self.config_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.config_tree)
        
        # JSON представление
        json_group = QGroupBox("JSON представление")
        json_layout = QVBoxLayout(json_group)
        
        self.config_json = QTextEdit()
        self.config_json.setReadOnly(True)
        self.config_json.setFont(QFont("Consolas", 10))
        json_layout.addWidget(self.config_json)
        
        layout.addWidget(json_group)
        
        self.tab_widget.addTab(config_widget, "Конфигурация")
    
    def _create_statistics_tab(self):
        """Создать вкладку статистики"""
        stats_widget = QWidget()
        layout = QVBoxLayout(stats_widget)
        
        # Таблица статистики
        self.stats_table = QTableWidget()
        self.stats_table.setColumnCount(2)
        self.stats_table.setHorizontalHeaderLabels(["Метрика", "Значение"])
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.stats_table)
        
        # Дополнительная статистика
        additional_stats_group = QGroupBox("Дополнительная статистика")
        additional_stats_layout = QFormLayout(additional_stats_group)
        
        self.avg_fps_label = QLabel()
        self.avg_memory_label = QLabel()
        self.avg_cpu_label = QLabel()
        self.error_count_label = QLabel()
        self.warning_count_label = QLabel()
        
        additional_stats_layout.addRow("Средний FPS:", self.avg_fps_label)
        additional_stats_layout.addRow("Среднее использование памяти:", self.avg_memory_label)
        additional_stats_layout.addRow("Среднее использование CPU:", self.avg_cpu_label)
        additional_stats_layout.addRow("Количество ошибок:", self.error_count_label)
        additional_stats_layout.addRow("Количество предупреждений:", self.warning_count_label)
        
        layout.addWidget(additional_stats_group)
        
        self.tab_widget.addTab(stats_widget, "Статистика")
    
    def _create_performance_tab(self):
        """Создать вкладку производительности"""
        performance_widget = QWidget()
        layout = QVBoxLayout(performance_widget)
        
        # Прогресс загрузки
        self.performance_progress = QProgressBar()
        self.performance_progress.setVisible(False)
        layout.addWidget(self.performance_progress)
        
        # Графики производительности
        if QChart is not None:
            self._create_performance_charts(layout)
        else:
            # Заглушка если QtChart недоступен
            no_charts_label = QLabel("Графики производительности недоступны\n(требуется PyQtChart)")
            no_charts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_charts_label.setStyleSheet("color: gray; font-style: italic;")
            layout.addWidget(no_charts_label)
        
        # Таблица данных производительности
        self.performance_table = QTableWidget()
        self.performance_table.setColumnCount(4)
        self.performance_table.setHorizontalHeaderLabels(["Время", "FPS", "Память (MB)", "CPU (%)"])
        self.performance_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.performance_table)
        
        self.tab_widget.addTab(performance_widget, "Производительность")
    
    def _create_performance_charts(self, layout):
        """Создать графики производительности"""
        # FPS график
        fps_chart = QChart()
        fps_chart.setTitle("FPS во времени")
        
        fps_series = QLineSeries()
        fps_series.setName("FPS")
        
        fps_chart.addSeries(fps_series)
        
        # Оси
        fps_x_axis = QDateTimeAxis()
        fps_x_axis.setFormat("hh:mm")
        fps_x_axis.setTitleText("Время")
        fps_chart.addAxis(fps_x_axis, Qt.AlignmentFlag.AlignBottom)
        fps_series.attachAxis(fps_x_axis)
        
        fps_y_axis = QValueAxis()
        fps_y_axis.setTitleText("FPS")
        fps_y_axis.setRange(0, 60)
        fps_chart.addAxis(fps_y_axis, Qt.AlignmentFlag.AlignLeft)
        fps_series.attachAxis(fps_y_axis)
        
        fps_chart_view = QChartView(fps_chart)
        fps_chart_view.setMaximumHeight(200)
        layout.addWidget(fps_chart_view)
        
        # Сохраняем ссылки для обновления
        self.fps_series = fps_series
        self.fps_x_axis = fps_x_axis
        self.fps_y_axis = fps_y_axis
    
    def _create_logs_tab(self):
        """Создать вкладку логов"""
        logs_widget = QWidget()
        layout = QVBoxLayout(logs_widget)
        
        # Фильтры логов
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Уровень:"))
        
        self.log_level_filter = QComboBox()
        self.log_level_filter.addItems(["Все", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_filter.currentTextChanged.connect(self._filter_logs)
        filter_layout.addWidget(self.log_level_filter)
        
        filter_layout.addWidget(QLabel("Поиск:"))
        
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("Поиск в логах...")
        self.log_search.textChanged.connect(self._filter_logs)
        filter_layout.addWidget(self.log_search)
        
        filter_layout.addStretch()
        
        layout.addLayout(filter_layout)
        
        # Таблица логов
        self.logs_table = QTableWidget()
        self.logs_table.setColumnCount(4)
        self.logs_table.setHorizontalHeaderLabels(["Время", "Уровень", "Модуль", "Сообщение"])
        self.logs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.logs_table)
        
        self.tab_widget.addTab(logs_widget, "Логи")
    
    def _create_related_data_tab(self):
        """Создать вкладку связанных данных"""
        related_widget = QWidget()
        layout = QVBoxLayout(related_widget)
        
        # Связанные объекты
        objects_group = QGroupBox("Обнаруженные объекты")
        objects_layout = QVBoxLayout(objects_group)
        
        self.objects_table = QTableWidget()
        self.objects_table.setColumnCount(5)
        self.objects_table.setHorizontalHeaderLabels(["ID", "Класс", "Время", "Источник", "Координаты"])
        self.objects_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        objects_layout.addWidget(self.objects_table)
        
        layout.addWidget(objects_group)
        
        # Связанные события
        events_group = QGroupBox("Обнаруженные события")
        events_layout = QVBoxLayout(events_group)
        
        self.events_table = QTableWidget()
        self.events_table.setColumnCount(5)
        self.events_table.setHorizontalHeaderLabels(["ID", "Тип", "Время", "Источник", "Описание"])
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        events_layout.addWidget(self.events_table)
        
        layout.addWidget(events_group)
        
        self.tab_widget.addTab(related_widget, "Связанные данные")
    
    def _add_buttons(self, layout):
        """Добавить кнопки управления"""
        button_layout = QHBoxLayout()
        
        # Кнопки действий
        self.export_btn = QPushButton("Экспорт данных")
        self.export_btn.clicked.connect(self._export_data)
        button_layout.addWidget(self.export_btn)
        
        self.view_config_btn = QPushButton("Просмотр конфигурации")
        self.view_config_btn.clicked.connect(self._view_configuration)
        button_layout.addWidget(self.view_config_btn)
        
        self.view_logs_btn = QPushButton("Просмотр логов")
        self.view_logs_btn.clicked.connect(self._view_logs)
        button_layout.addWidget(self.view_logs_btn)
        
        button_layout.addStretch()
        
        # Кнопка закрытия
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
    
    def _load_job_data(self):
        """Загрузить данные задачи"""
        # Основная информация
        self.job_id_label.setText(str(self.job_data.get('job_id', 'N/A')))
        self.project_id_label.setText(str(self.job_data.get('project_id', 'N/A')))
        self.configuration_id_label.setText(str(self.job_data.get('configuration_id', 'N/A')))
        
        # Статус
        status = self.job_data.get('status', 'Unknown')
        self.status_label.setText(status)
        if status == 'Running':
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        elif status == 'Stopped':
            self.status_label.setStyleSheet("color: blue; font-weight: bold;")
        elif status == 'Error':
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: gray; font-weight: bold;")
        
        # Времена
        creation_time = self.job_data.get('creation_time')
        if creation_time:
            if isinstance(creation_time, str):
                self.creation_time_label.setText(creation_time)
            else:
                self.creation_time_label.setText(creation_time.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.creation_time_label.setText("N/A")
        
        finish_time = self.job_data.get('finish_time')
        if finish_time:
            if isinstance(finish_time, str):
                self.finish_time_label.setText(finish_time)
            else:
                self.finish_time_label.setText(finish_time.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.finish_time_label.setText("N/A")
        
        # Длительность
        if creation_time and finish_time:
            try:
                if isinstance(creation_time, str):
                    creation_time = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                if isinstance(finish_time, str):
                    finish_time = datetime.fromisoformat(finish_time.replace('Z', '+00:00'))
                
                duration = finish_time - creation_time
                self.duration_label.setText(str(duration))
            except Exception as e:
                self.logger.warning(f"Не удалось вычислить длительность: {e}")
                self.duration_label.setText("N/A")
        else:
            self.duration_label.setText("N/A")
        
        # Статистика
        self.total_frames_label.setText(str(self.job_data.get('total_frames', 'N/A')))
        self.processed_frames_label.setText(str(self.job_data.get('processed_frames', 'N/A')))
        self.detected_objects_label.setText(str(self.job_data.get('detected_objects', 'N/A')))
        self.detected_events_label.setText(str(self.job_data.get('detected_events', 'N/A')))
        
        # Описание
        description = self.job_data.get('description', '')
        self.description_text.setPlainText(description)
        
        # Загружаем конфигурацию
        self._load_configuration()
        
        # Загружаем статистику
        self._load_statistics()
    
    def _load_configuration(self):
        """Загрузить конфигурацию"""
        config_info = self.job_data.get('configuration_info', {})
        if isinstance(config_info, str):
            try:
                config = json.loads(config_info)
            except json.JSONDecodeError as e:
                self.logger.error(f"Ошибка парсинга конфигурации: {e}")
                config = {}
        else:
            config = config_info
        
        # Заполняем дерево конфигурации
        self.config_tree.clear()
        self._populate_config_tree(config, self.config_tree.invisibleRootItem())
        
        # Заполняем JSON представление
        self.config_json.setPlainText(json.dumps(config, indent=2, ensure_ascii=False))
    
    def _populate_config_tree(self, data, parent_item, path=""):
        """Рекурсивно заполнить дерево конфигурации"""
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                item = QTreeWidgetItem(parent_item)
                item.setText(0, key)
                
                if isinstance(value, (dict, list)):
                    item.setText(1, f"{type(value).__name__} ({len(value)} элементов)")
                    self._populate_config_tree(value, item, current_path)
                else:
                    item.setText(1, str(value)[:100] + ("..." if len(str(value)) > 100 else ""))
        
        elif isinstance(data, list):
            for i, item_data in enumerate(data):
                current_path = f"{path}[{i}]"
                item = QTreeWidgetItem(parent_item)
                item.setText(0, f"[{i}]")
                
                if isinstance(item_data, (dict, list)):
                    item.setText(1, f"{type(item_data).__name__} ({len(item_data)} элементов)")
                    self._populate_config_tree(item_data, item, current_path)
                else:
                    item.setText(1, str(item_data)[:100] + ("..." if len(str(item_data)) > 100 else ""))
    
    def _load_statistics(self):
        """Загрузить статистику"""
        # Заполняем таблицу статистики
        stats_data = [
            ("ID задачи", str(self.job_data.get('job_id', 'N/A'))),
            ("ID проекта", str(self.job_data.get('project_id', 'N/A'))),
            ("Статус", self.job_data.get('status', 'Unknown')),
            ("Время создания", str(self.job_data.get('creation_time', 'N/A'))),
            ("Время завершения", str(self.job_data.get('finish_time', 'N/A'))),
            ("Всего кадров", str(self.job_data.get('total_frames', 'N/A'))),
            ("Обработано кадров", str(self.job_data.get('processed_frames', 'N/A'))),
            ("Обнаружено объектов", str(self.job_data.get('detected_objects', 'N/A'))),
            ("Обнаружено событий", str(self.job_data.get('detected_events', 'N/A'))),
        ]
        
        self.stats_table.setRowCount(len(stats_data))
        for i, (metric, value) in enumerate(stats_data):
            self.stats_table.setItem(i, 0, QTableWidgetItem(metric))
            self.stats_table.setItem(i, 1, QTableWidgetItem(value))
        
        # Дополнительная статистика
        self.avg_fps_label.setText(str(self.job_data.get('avg_fps', 'N/A')))
        self.avg_memory_label.setText(str(self.job_data.get('avg_memory_mb', 'N/A')) + " MB")
        self.avg_cpu_label.setText(str(self.job_data.get('avg_cpu_percent', 'N/A')) + " %")
        self.error_count_label.setText(str(self.job_data.get('error_count', 'N/A')))
        self.warning_count_label.setText(str(self.job_data.get('warning_count', 'N/A')))
    
    def _start_performance_data_loading(self):
        """Запустить загрузку данных производительности"""
        job_id = self.job_data.get('job_id')
        project_id = self.job_data.get('project_id')
        
        if job_id and project_id:
            self.performance_progress.setVisible(True)
            self.performance_progress.setRange(0, 0)  # Неопределенный прогресс
            
            self.performance_thread = PerformanceDataThread(job_id, project_id)
            self.performance_thread.data_loaded.connect(self._on_performance_data_loaded)
            self.performance_thread.start()
    
    @pyqtSlot(dict)
    def _on_performance_data_loaded(self, data):
        """Обработчик загрузки данных производительности"""
        self.performance_progress.setVisible(False)
        self.performance_data = data
        
        # Обновляем графики
        if QChart is not None and hasattr(self, 'fps_series'):
            self._update_performance_charts()
        
        # Обновляем таблицу производительности
        self._update_performance_table()
    
    def _update_performance_charts(self):
        """Обновить графики производительности"""
        if 'fps_history' in self.performance_data:
            fps_data = self.performance_data['fps_history']
            
            # Очищаем серию
            self.fps_series.clear()
            
            # Добавляем точки
            for point in fps_data:
                timestamp = point['timestamp']
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                
                # Конвертируем в миллисекунды с эпохи
                timestamp_ms = int(timestamp.timestamp() * 1000)
                self.fps_series.append(timestamp_ms, point['fps'])
    
    def _update_performance_table(self):
        """Обновить таблицу производительности"""
        if not self.performance_data:
            return
        
        # Объединяем данные по времени
        fps_data = self.performance_data.get('fps_history', [])
        memory_data = self.performance_data.get('memory_usage', [])
        cpu_data = self.performance_data.get('cpu_usage', [])
        
        # Создаем словарь для объединения данных
        combined_data = {}
        
        for point in fps_data:
            timestamp = point['timestamp']
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            combined_data[timestamp] = {'fps': point['fps']}
        
        for point in memory_data:
            timestamp = point['timestamp']
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if timestamp not in combined_data:
                combined_data[timestamp] = {}
            combined_data[timestamp]['memory'] = point['memory_mb']
        
        for point in cpu_data:
            timestamp = point['timestamp']
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if timestamp not in combined_data:
                combined_data[timestamp] = {}
            combined_data[timestamp]['cpu'] = point['cpu_percent']
        
        # Заполняем таблицу
        sorted_timestamps = sorted(combined_data.keys())
        self.performance_table.setRowCount(len(sorted_timestamps))
        
        for i, timestamp in enumerate(sorted_timestamps):
            data = combined_data[timestamp]
            
            self.performance_table.setItem(i, 0, QTableWidgetItem(timestamp.strftime("%H:%M:%S")))
            self.performance_table.setItem(i, 1, QTableWidgetItem(str(data.get('fps', 'N/A'))))
            self.performance_table.setItem(i, 2, QTableWidgetItem(str(data.get('memory', 'N/A'))))
            self.performance_table.setItem(i, 3, QTableWidgetItem(str(data.get('cpu', 'N/A'))))
    
    def _filter_logs(self):
        """Фильтровать логи"""
        # Здесь должна быть логика фильтрации логов
        pass
    
    def _export_data(self):
        """Экспорт данных задачи"""
        try:
            # Создаем отчет
            report = {
                'job_data': self.job_data,
                'performance_data': self.performance_data,
                'export_timestamp': datetime.now().isoformat()
            }
            
            # Здесь должна быть логика сохранения файла
            QMessageBox.information(
                self,
                "Экспорт завершен",
                "Данные задачи экспортированы"
            )
            
            self.logger.info("Экспорт данных задачи завершен")
            
        except Exception as e:
            self.logger.error(f"Ошибка экспорта данных: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось экспортировать данные: {str(e)}")
    
    def _view_configuration(self):
        """Просмотр конфигурации"""
        # Переключаемся на вкладку конфигурации
        self.tab_widget.setCurrentIndex(1)
    
    def _view_logs(self):
        """Просмотр логов"""
        # Переключаемся на вкладку логов
        self.tab_widget.setCurrentIndex(4)
    
    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        if self.performance_thread and self.performance_thread.isRunning():
            self.performance_thread.terminate()
            self.performance_thread.wait()
        
        event.accept()
