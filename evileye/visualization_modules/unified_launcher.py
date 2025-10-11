"""
Unified Launcher Window for EvilEye GUI

Единое окно-лаунчер для выбора режима работы: Configure или Run.
Альтернативное решение для запуска приложения.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from PyQt6.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QListWidget, QListWidgetItem, QGroupBox, QGridLayout,
        QFileDialog, QMessageBox, QTextEdit, QSplitter, QFrame, QTabWidget
    )
    from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QThread
    from PyQt6.QtGui import QFont, QIcon, QPixmap
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QComboBox, QListWidget, QListWidgetItem, QGroupBox, QGridLayout,
        QFileDialog, QMessageBox, QTextEdit, QSplitter, QFrame, QTabWidget
    )
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QThread
    from PyQt5.QtGui import QFont, QIcon, QPixmap
    pyqt_version = 5

from ..core.logger import get_module_logger
from ..utils import utils
from .base_window import BaseMainWindow
from .configurer.configurer_window import ConfigurerMainWindow
from .window_manager import get_window_manager


class ConfigLoaderThread(QThread):
    """Поток для загрузки конфигураций в фоне"""
    
    configs_loaded = pyqtSignal(list)  # Список конфигураций
    
    def __init__(self, configs_dir: str):
        super().__init__()
        self.configs_dir = configs_dir
        self.logger = get_module_logger("config_loader_thread")
    
    def run(self):
        """Загрузка конфигураций"""
        try:
            configs = []
            config_path = Path(self.configs_dir)
            
            if config_path.exists():
                for config_file in config_path.glob("*.json"):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                        
                        # Извлекаем информацию о конфигурации
                        config_info = {
                            'name': config_file.stem,
                            'path': str(config_file),
                            'description': self._get_config_description(config_data),
                            'sources_count': len(config_data.get('pipeline', {}).get('sources', [])),
                            'last_modified': config_file.stat().st_mtime
                        }
                        configs.append(config_info)
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to load config {config_file}: {e}")
            
            # Сортируем по времени изменения (новые сверху)
            configs.sort(key=lambda x: x['last_modified'], reverse=True)
            
            self.configs_loaded.emit(configs)
            
        except Exception as e:
            self.logger.error(f"Error loading configs: {e}")
            self.configs_loaded.emit([])
    
    def _get_config_description(self, config_data: Dict[str, Any]) -> str:
        """Получить описание конфигурации"""
        try:
            pipeline = config_data.get('pipeline', {})
            sources = pipeline.get('sources', [])
            
            if not sources:
                return "No sources configured"
            
            source_types = []
            for source in sources:
                source_type = source.get('source', 'unknown')
                source_types.append(source_type)
            
            return f"{len(sources)} source(s): {', '.join(set(source_types))}"
            
        except Exception:
            return "Invalid configuration"


class UnifiedLauncherWindow(BaseMainWindow):
    """
    Единое окно-лаунчер для EvilEye.
    
    Предоставляет выбор между режимами:
    - Configure: Открытие окна настроек
    - Run: Запуск приложения с выбранной конфигурацией
    """
    
    # Сигналы
    config_selected = pyqtSignal(str)  # Путь к выбранной конфигурации
    mode_changed = pyqtSignal(str)  # Изменение режима (configure/run)
    
    def __init__(self, parent=None):
        super().__init__(
            window_id="unified_launcher",
            window_type="launcher",
            config_file=None,
            parent=parent
        )
        
        self.logger = get_module_logger("unified_launcher")
        self.set_window_title("EvilEye - Unified Launcher")
        self.resize(900, 700)
        
        # Состояние
        self.current_mode = "run"  # "configure" или "run"
        self.selected_config = None
        self.configs = []
        self.config_loader_thread = None
        self.configurer_window = None
        
        # Настройки
        self.configs_dir = "configs"
        self.recent_configs_file = "recent_configs.json"
        self.recent_configs = self._load_recent_configs()
        
        # Инициализация UI
        self._init_ui()
        self._load_configs()
        
        self.logger.info("UnifiedLauncherWindow initialized")
    
    def _init_ui(self) -> None:
        """Инициализация пользовательского интерфейса"""
        # Создаем центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Заголовок
        title_label = QLabel("EvilEye - Unified Launcher")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 20px;")
        main_layout.addWidget(title_label)
        
        # Создаем splitter для разделения на панели
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Левая панель - выбор режима и конфигурации
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        # Правая панель - информация и предпросмотр
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        # Устанавливаем пропорции splitter
        splitter.setSizes([400, 500])
        
        # Панель кнопок
        button_panel = self._create_button_panel()
        main_layout.addWidget(button_panel)
    
    def _create_left_panel(self) -> QWidget:
        """Создание левой панели с выбором режима и конфигурации"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(15)
        
        # Группа выбора режима
        mode_group = QGroupBox("Режим работы")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Run - Запуск приложения", "Configure - Настройка конфигурации"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        
        layout.addWidget(mode_group)
        
        # Группа выбора конфигурации
        config_group = QGroupBox("Конфигурация")
        config_layout = QVBoxLayout(config_group)
        
        # Кнопки управления конфигурациями
        config_buttons_layout = QHBoxLayout()
        
        self.browse_config_btn = QPushButton("Обзор...")
        self.browse_config_btn.clicked.connect(self._browse_config)
        config_buttons_layout.addWidget(self.browse_config_btn)
        
        self.refresh_configs_btn = QPushButton("Обновить")
        self.refresh_configs_btn.clicked.connect(self._load_configs)
        config_buttons_layout.addWidget(self.refresh_configs_btn)
        
        config_buttons_layout.addStretch()
        config_layout.addLayout(config_buttons_layout)
        
        # Список конфигураций
        self.config_list = QListWidget()
        self.config_list.itemSelectionChanged.connect(self._on_config_selected)
        self.config_list.itemDoubleClicked.connect(self._on_config_double_clicked)
        config_layout.addWidget(self.config_list)
        
        # Информация о выбранной конфигурации
        self.config_info_label = QLabel("Выберите конфигурацию")
        self.config_info_label.setWordWrap(True)
        self.config_info_label.setStyleSheet("color: #666; font-size: 11px;")
        config_layout.addWidget(self.config_info_label)
        
        layout.addWidget(config_group)
        
        # Группа недавних конфигураций
        recent_group = QGroupBox("Недавние конфигурации")
        recent_layout = QVBoxLayout(recent_group)
        
        self.recent_list = QListWidget()
        self.recent_list.itemClicked.connect(self._on_recent_config_clicked)
        recent_layout.addWidget(self.recent_list)
        
        layout.addWidget(recent_group)
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """Создание правой панели с информацией и предпросмотром"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(15)
        
        # Группа информации о конфигурации
        info_group = QGroupBox("Информация о конфигурации")
        info_layout = QVBoxLayout(info_group)
        
        self.config_details = QTextEdit()
        self.config_details.setReadOnly(True)
        self.config_details.setMaximumHeight(200)
        self.config_details.setPlaceholderText("Выберите конфигурацию для просмотра деталей")
        info_layout.addWidget(self.config_details)
        
        layout.addWidget(info_group)
        
        # Группа предпросмотра
        preview_group = QGroupBox("Предпросмотр")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Предпросмотр конфигурации появится здесь")
        preview_layout.addWidget(self.preview_text)
        
        layout.addWidget(preview_group)
        
        return panel
    
    def _create_button_panel(self) -> QWidget:
        """Создание панели кнопок"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Кнопка запуска
        self.launch_btn = QPushButton("Запустить")
        self.launch_btn.setMinimumSize(120, 40)
        self.launch_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:pressed {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.launch_btn.clicked.connect(self._launch_selected_mode)
        layout.addWidget(self.launch_btn)
        
        layout.addStretch()
        
        # Кнопка выхода
        self.exit_btn = QPushButton("Выход")
        self.exit_btn.setMinimumSize(100, 40)
        self.exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #ec7063;
            }
            QPushButton:pressed {
                background-color: #c0392b;
            }
        """)
        self.exit_btn.clicked.connect(self.close)
        layout.addWidget(self.exit_btn)
        
        return panel
    
    def _load_configs(self) -> None:
        """Загрузка списка конфигураций"""
        if self.config_loader_thread and self.config_loader_thread.isRunning():
            return
        
        self.config_loader_thread = ConfigLoaderThread(self.configs_dir)
        self.config_loader_thread.configs_loaded.connect(self._on_configs_loaded)
        self.config_loader_thread.start()
        
        # Показываем индикатор загрузки
        self.config_info_label.setText("Загрузка конфигураций...")
    
    @pyqtSlot(list)
    def _on_configs_loaded(self, configs: List[Dict[str, Any]]) -> None:
        """Обработка загруженных конфигураций"""
        self.configs = configs
        self.config_list.clear()
        
        for config in configs:
            item = QListWidgetItem(config['name'])
            item.setData(Qt.ItemDataRole.UserRole, config)
            item.setToolTip(f"{config['description']}\nПуть: {config['path']}")
            self.config_list.addItem(item)
        
        # Обновляем список недавних конфигураций
        self._update_recent_configs_list()
        
        if configs:
            self.config_info_label.setText(f"Найдено {len(configs)} конфигураций")
        else:
            self.config_info_label.setText("Конфигурации не найдены")
    
    def _update_recent_configs_list(self) -> None:
        """Обновление списка недавних конфигураций"""
        self.recent_list.clear()
        
        for config_path in self.recent_configs:
            config_name = Path(config_path).stem
            item = QListWidgetItem(config_name)
            item.setData(Qt.ItemDataRole.UserRole, config_path)
            item.setToolTip(f"Путь: {config_path}")
            self.recent_list.addItem(item)
    
    @pyqtSlot()
    def _on_mode_changed(self) -> None:
        """Обработка изменения режима"""
        mode_text = self.mode_combo.currentText()
        if "Configure" in mode_text:
            self.current_mode = "configure"
            self.launch_btn.setText("Открыть настройки")
        else:
            self.current_mode = "run"
            self.launch_btn.setText("Запустить приложение")
        
        self.mode_changed.emit(self.current_mode)
        self.logger.debug(f"Mode changed to: {self.current_mode}")
    
    @pyqtSlot()
    def _on_config_selected(self) -> None:
        """Обработка выбора конфигурации"""
        current_item = self.config_list.currentItem()
        if not current_item:
            self.selected_config = None
            self._update_config_info()
            return
        
        config_data = current_item.data(Qt.ItemDataRole.UserRole)
        self.selected_config = config_data['path']
        
        self._update_config_info()
        self._update_config_preview()
        
        # Добавляем в недавние конфигурации
        self._add_to_recent_configs(self.selected_config)
    
    @pyqtSlot(QListWidgetItem)
    def _on_config_double_clicked(self, item: QListWidgetItem) -> None:
        """Обработка двойного клика по конфигурации"""
        self._launch_selected_mode()
    
    @pyqtSlot(QListWidgetItem)
    def _on_recent_config_clicked(self, item: QListWidgetItem) -> None:
        """Обработка клика по недавней конфигурации"""
        config_path = item.data(Qt.ItemDataRole.UserRole)
        
        # Ищем конфигурацию в основном списке
        for i in range(self.config_list.count()):
            list_item = self.config_list.item(i)
            config_data = list_item.data(Qt.ItemDataRole.UserRole)
            if config_data['path'] == config_path:
                self.config_list.setCurrentItem(list_item)
                break
    
    @pyqtSlot()
    def _browse_config(self) -> None:
        """Обзор файлов конфигурации"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл конфигурации",
            self.configs_dir,
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.selected_config = file_path
            self._add_to_recent_configs(file_path)
            self._update_config_info()
            self._update_config_preview()
    
    def _update_config_info(self) -> None:
        """Обновление информации о конфигурации"""
        if not self.selected_config:
            self.config_info_label.setText("Выберите конфигурацию")
            self.config_details.clear()
            return
        
        try:
            config_path = Path(self.selected_config)
            if not config_path.exists():
                self.config_info_label.setText("Файл конфигурации не найден")
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Формируем информацию о конфигурации
            info_text = f"Файл: {config_path.name}\n"
            info_text += f"Путь: {config_path}\n"
            info_text += f"Размер: {config_path.stat().st_size} байт\n"
            info_text += f"Изменен: {config_path.stat().st_mtime}\n\n"
            
            # Информация о pipeline
            pipeline = config_data.get('pipeline', {})
            sources = pipeline.get('sources', [])
            info_text += f"Источники: {len(sources)}\n"
            
            for i, source in enumerate(sources):
                source_type = source.get('source', 'unknown')
                info_text += f"  {i+1}. {source_type}\n"
            
            # Информация о детекторах
            detectors = config_data.get('detectors', [])
            info_text += f"\nДетекторы: {len(detectors)}\n"
            
            # Информация о трекерах
            trackers = config_data.get('trackers', [])
            info_text += f"Трекеры: {len(trackers)}\n"
            
            self.config_details.setPlainText(info_text)
            self.config_info_label.setText(f"Выбрано: {config_path.name}")
            
        except Exception as e:
            self.logger.error(f"Error updating config info: {e}")
            self.config_info_label.setText(f"Ошибка загрузки: {str(e)}")
    
    def _update_config_preview(self) -> None:
        """Обновление предпросмотра конфигурации"""
        if not self.selected_config:
            self.preview_text.clear()
            return
        
        try:
            with open(self.selected_config, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Форматируем JSON для предпросмотра
            preview_json = json.dumps(config_data, indent=2, ensure_ascii=False)
            self.preview_text.setPlainText(preview_json)
            
        except Exception as e:
            self.logger.error(f"Error updating config preview: {e}")
            self.preview_text.setPlainText(f"Ошибка загрузки конфигурации: {str(e)}")
    
    @pyqtSlot()
    def _launch_selected_mode(self) -> None:
        """Запуск выбранного режима"""
        if self.current_mode == "configure":
            self._launch_configurer()
        else:
            self._launch_application()
    
    def _launch_configurer(self) -> None:
        """Запуск окна настроек"""
        try:
            if not self.selected_config:
                QMessageBox.warning(
                    self,
                    "Предупреждение",
                    "Пожалуйста, выберите конфигурацию для редактирования"
                )
                return
            
            # Создаем окно настроек
            self.configurer_window = ConfigurerMainWindow(
                config_file_name=self.selected_config,
                win_width=1280,
                win_height=720,
                parent=self
            )
            
            # Подключаем сигналы
            self.configurer_window.window_closed.connect(self._on_configurer_closed)
            
            # Показываем окно
            self.configurer_window.show()
            self.configurer_window.raise_()
            self.configurer_window.activateWindow()
            
            self.logger.info(f"Configurer launched for: {self.selected_config}")
            
        except Exception as e:
            self.logger.error(f"Error launching configurer: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть окно настроек:\n{str(e)}"
            )
    
    def _launch_application(self) -> None:
        """Запуск приложения"""
        try:
            if not self.selected_config:
                QMessageBox.warning(
                    self,
                    "Предупреждение",
                    "Пожалуйста, выберите конфигурацию для запуска"
                )
                return
            
            # Получаем путь к process.py
            project_root = Path(__file__).parent.parent.parent
            process_script = project_root / "evileye" / "process.py"
            
            if not process_script.exists():
                QMessageBox.critical(
                    self,
                    "Ошибка",
                    f"Файл process.py не найден по пути: {process_script}"
                )
                return
            
            # Запускаем приложение
            cmd = [sys.executable, str(process_script), "--config", self.selected_config, "--gui"]
            
            self.logger.info(f"Launching application with command: {' '.join(cmd)}")
            
            # Запускаем в фоне
            subprocess.Popen(cmd, cwd=project_root)
            
            # Закрываем лаунчер
            self.close()
            
        except Exception as e:
            self.logger.error(f"Error launching application: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось запустить приложение:\n{str(e)}"
            )
    
    @pyqtSlot()
    def _on_configurer_closed(self) -> None:
        """Обработка закрытия окна настроек"""
        self.configurer_window = None
        self.logger.debug("Configurer window closed")
    
    def _add_to_recent_configs(self, config_path: str) -> None:
        """Добавление конфигурации в список недавних"""
        if config_path in self.recent_configs:
            self.recent_configs.remove(config_path)
        
        self.recent_configs.insert(0, config_path)
        
        # Ограничиваем количество недавних конфигураций
        if len(self.recent_configs) > 10:
            self.recent_configs = self.recent_configs[:10]
        
        self._save_recent_configs()
        self._update_recent_configs_list()
    
    def _load_recent_configs(self) -> List[str]:
        """Загрузка списка недавних конфигураций"""
        try:
            if os.path.exists(self.recent_configs_file):
                with open(self.recent_configs_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.warning(f"Error loading recent configs: {e}")
        
        return []
    
    def _save_recent_configs(self) -> None:
        """Сохранение списка недавних конфигураций"""
        try:
            with open(self.recent_configs_file, 'w', encoding='utf-8') as f:
                json.dump(self.recent_configs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.warning(f"Error saving recent configs: {e}")
    
    # === Реализация абстрактных методов BaseMainWindow ===
    
    def get_config_data(self) -> Optional[Dict[str, Any]]:
        """Получить данные конфигурации для сохранения"""
        return {
            'recent_configs': self.recent_configs,
            'configs_dir': self.configs_dir,
            'last_mode': self.current_mode
        }
    
    def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
        """Применить данные конфигурации"""
        try:
            self.recent_configs = config_data.get('recent_configs', [])
            self.configs_dir = config_data.get('configs_dir', 'configs')
            self.current_mode = config_data.get('last_mode', 'run')
            
            # Обновляем UI
            self._update_recent_configs_list()
            if self.current_mode == "configure":
                self.mode_combo.setCurrentIndex(1)
            else:
                self.mode_combo.setCurrentIndex(0)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error applying config data: {e}")
            return False
    
    def on_config_changed(self, config_file: str) -> None:
        """Обработчик изменения конфигурации"""
        self.logger.debug(f"Configuration changed: {config_file}")
        # Можно добавить логику для обновления списка конфигураций
