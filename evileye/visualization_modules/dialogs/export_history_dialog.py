import json
import csv
import html
from datetime import datetime
try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
        QComboBox, QCheckBox, QDateEdit, QTimeEdit, QDateTimeEdit,
        QPushButton, QDialogButtonBox, QLabel, QLineEdit, QTextEdit,
        QListWidget, QListWidgetItem, QSpinBox, QFileDialog, QMessageBox
    )
    from PyQt6.QtCore import Qt, QDate, QTime, QDateTime
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
        QComboBox, QCheckBox, QDateEdit, QTimeEdit, QDateTimeEdit,
        QPushButton, QDialogButtonBox, QLabel, QLineEdit, QTextEdit,
        QListWidget, QListWidgetItem, QSpinBox, QFileDialog, QMessageBox
    )
    from PyQt5.QtCore import Qt, QDate, QTime, QDateTime
    pyqt_version = 5


class ExportHistoryDialog(QDialog):
    """Диалог для экспорта истории конфигураций в различных форматах"""
    
    def __init__(self, config_history_manager, parent=None):
        super().__init__(parent)
        self.config_history_manager = config_history_manager
        self.setWindowTitle("Экспорт истории конфигураций")
        self.setModal(True)
        self.resize(600, 500)
        
        self._setup_ui()
        self._load_available_projects()
        
    def _setup_ui(self):
        """Настройка пользовательского интерфейса"""
        layout = QVBoxLayout(self)
        
        # Формат экспорта
        format_group = QGroupBox("Формат экспорта")
        format_layout = QFormLayout(format_group)
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JSON", "CSV", "HTML"])
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        format_layout.addRow("Формат:", self.format_combo)
        
        # Опции формата
        self.include_configs_check = QCheckBox("Включить полные конфигурации")
        self.include_configs_check.setChecked(True)
        self.include_configs_check.setToolTip("Включить полные JSON конфигурации в экспорт")
        format_layout.addRow("", self.include_configs_check)
        
        self.include_stats_check = QCheckBox("Включить статистику")
        self.include_stats_check.setChecked(True)
        self.include_stats_check.setToolTip("Включить статистику по задачам")
        format_layout.addRow("", self.include_stats_check)
        
        self.pretty_format_check = QCheckBox("Красивое форматирование")
        self.pretty_format_check.setChecked(True)
        self.pretty_format_check.setToolTip("Использовать отступы и переносы строк")
        format_layout.addRow("", self.pretty_format_check)
        
        layout.addWidget(format_group)
        
        # Фильтры
        filters_group = QGroupBox("Фильтры")
        filters_layout = QFormLayout(filters_group)
        
        # Проекты
        self.projects_list = QListWidget()
        self.projects_list.setMaximumHeight(100)
        self.projects_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        filters_layout.addRow("Проекты:", self.projects_list)
        
        # Статусы
        self.status_list = QListWidget()
        self.status_list.setMaximumHeight(100)
        self.status_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        status_items = ["Running", "Stopped", "Error", "Unknown"]
        for status in status_items:
            item = QListWidgetItem(status)
            item.setCheckState(Qt.CheckState.Checked)
            self.status_list.addItem(item)
        filters_layout.addRow("Статусы:", self.status_list)
        
        # Диапазон дат
        self.date_from = QDateTimeEdit()
        self.date_from.setDateTime(QDateTime.currentDateTime().addDays(-30))
        self.date_from.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        filters_layout.addRow("С даты:", self.date_from)
        
        self.date_to = QDateTimeEdit()
        self.date_to.setDateTime(QDateTime.currentDateTime())
        self.date_to.setDisplayFormat("yyyy-MM-dd hh:mm:ss")
        filters_layout.addRow("По дату:", self.date_to)
        
        # Лимит записей
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(1000)
        self.limit_spin.setSpecialValueText("Без ограничений")
        self.limit_spin.setToolTip("Максимальное количество записей для экспорта")
        filters_layout.addRow("Лимит записей:", self.limit_spin)
        
        layout.addWidget(filters_group)
        
        # Поля для экспорта
        fields_group = QGroupBox("Поля для экспорта")
        fields_layout = QVBoxLayout(fields_group)
        
        self.fields_list = QListWidget()
        self.fields_list.setMaximumHeight(120)
        self.fields_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        
        # Добавляем доступные поля
        available_fields = [
            "job_id", "project_id", "configuration_id", "status", 
            "creation_time", "finish_time", "duration", "frames_processed",
            "objects_detected", "events_detected", "configuration_info"
        ]
        
        for field in available_fields:
            item = QListWidgetItem(field)
            item.setCheckState(Qt.CheckState.Checked)
            self.fields_list.addItem(item)
        
        fields_layout.addWidget(self.fields_list)
        layout.addWidget(fields_group)
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("Предпросмотр")
        self.preview_btn.clicked.connect(self._preview_export)
        button_layout.addWidget(self.preview_btn)
        
        self.export_btn = QPushButton("Экспорт")
        self.export_btn.clicked.connect(self._export_data)
        button_layout.addWidget(self.export_btn)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        
    def _load_available_projects(self):
        """Загрузить доступные проекты"""
        try:
            if self.config_history_manager:
                projects = self.config_history_manager.get_projects_list()
                for project in projects:
                    project_id = project.get('project_id', 'unknown')
                    project_name = project.get('project_name', f'Project {project_id}')
                    item = QListWidgetItem(f"{project_name} (ID: {project_id})")
                    item.setData(Qt.ItemDataRole.UserRole, project_id)
                    item.setCheckState(Qt.CheckState.Checked)
                    self.projects_list.addItem(item)
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить проекты: {str(e)}")
    
    def _on_format_changed(self, format_name):
        """Обработка изменения формата"""
        # Показываем/скрываем опции в зависимости от формата
        if format_name == "JSON":
            self.pretty_format_check.setVisible(True)
            self.include_configs_check.setVisible(True)
        elif format_name == "CSV":
            self.pretty_format_check.setVisible(False)
            self.include_configs_check.setVisible(False)
        elif format_name == "HTML":
            self.pretty_format_check.setVisible(True)
            self.include_configs_check.setVisible(True)
    
    def _preview_export(self):
        """Предпросмотр экспорта"""
        try:
            # Получаем параметры экспорта
            export_params = self._get_export_params()
            
            # Получаем данные для предпросмотра (первые 5 записей)
            preview_params = export_params.copy()
            preview_params['limit'] = 5
            
            data = self.config_history_manager.get_config_history(**preview_params)
            
            if not data:
                QMessageBox.information(self, "Предпросмотр", "Нет данных для экспорта с выбранными фильтрами")
                return
            
            # Создаем диалог предпросмотра
            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("Предпросмотр экспорта")
            preview_dialog.setModal(True)
            preview_dialog.resize(800, 600)
            
            layout = QVBoxLayout(preview_dialog)
            
            # Текстовое поле с предпросмотром
            preview_text = QTextEdit()
            preview_text.setReadOnly(True)
            
            # Форматируем данные в зависимости от выбранного формата
            format_name = self.format_combo.currentText()
            if format_name == "JSON":
                preview_content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            elif format_name == "CSV":
                preview_content = self._format_as_csv(data)
            elif format_name == "HTML":
                preview_content = self._format_as_html(data)
            
            preview_text.setPlainText(preview_content)
            layout.addWidget(preview_text)
            
            # Кнопка закрытия
            close_btn = QPushButton("Закрыть")
            close_btn.clicked.connect(preview_dialog.accept)
            layout.addWidget(close_btn)
            
            preview_dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при создании предпросмотра: {str(e)}")
    
    def _export_data(self):
        """Экспорт данных"""
        try:
            # Выбираем файл для сохранения
            format_name = self.format_combo.currentText()
            file_extensions = {
                "JSON": "JSON файлы (*.json);;Все файлы (*)",
                "CSV": "CSV файлы (*.csv);;Все файлы (*)",
                "HTML": "HTML файлы (*.html);;Все файлы (*)"
            }
            
            default_filename = f"config_history_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_name.lower()}"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                f"Экспорт истории в формате {format_name}",
                default_filename,
                file_extensions[format_name]
            )
            
            if not file_path:
                return
            
            # Получаем параметры экспорта
            export_params = self._get_export_params()
            
            # Получаем данные
            data = self.config_history_manager.get_config_history(**export_params)
            
            if not data:
                QMessageBox.information(self, "Экспорт", "Нет данных для экспорта с выбранными фильтрами")
                return
            
            # Экспортируем в выбранном формате
            if format_name == "JSON":
                self._export_json(data, file_path)
            elif format_name == "CSV":
                self._export_csv(data, file_path)
            elif format_name == "HTML":
                self._export_html(data, file_path)
            
            QMessageBox.information(
                self,
                "Успех",
                f"Данные успешно экспортированы в файл:\n{file_path}\n\n"
                f"Записей экспортировано: {len(data)}"
            )
            
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при экспорте: {str(e)}")
    
    def _get_export_params(self):
        """Получить параметры экспорта"""
        # Получаем выбранные проекты
        selected_projects = []
        for i in range(self.projects_list.count()):
            item = self.projects_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                project_id = item.data(Qt.ItemDataRole.UserRole)
                selected_projects.append(project_id)
        
        # Получаем выбранные статусы
        selected_statuses = []
        for i in range(self.status_list.count()):
            item = self.status_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_statuses.append(item.text())
        
        # Получаем выбранные поля
        selected_fields = []
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_fields.append(item.text())
        
        return {
            'project_ids': selected_projects if selected_projects else None,
            'statuses': selected_statuses if selected_statuses else None,
            'date_from': self.date_from.dateTime().toPython(),
            'date_to': self.date_to.dateTime().toPython(),
            'limit': self.limit_spin.value() if self.limit_spin.value() > 0 else None,
            'include_configs': self.include_configs_check.isChecked(),
            'include_stats': self.include_stats_check.isChecked(),
            'fields': selected_fields if selected_fields else None
        }
    
    def _format_as_csv(self, data):
        """Форматировать данные как CSV для предпросмотра"""
        if not data:
            return ""
        
        # Получаем заголовки из первой записи
        headers = list(data[0].keys())
        
        # Создаем CSV строку
        csv_lines = [','.join(headers)]
        for record in data:
            row = []
            for header in headers:
                value = record.get(header, '')
                # Экранируем значения с запятыми
                if isinstance(value, str) and ',' in value:
                    value = f'"{value}"'
                row.append(str(value))
            csv_lines.append(','.join(row))
        
        return '\n'.join(csv_lines)
    
    def _format_as_html(self, data):
        """Форматировать данные как HTML для предпросмотра"""
        if not data:
            return ""
        
        html_lines = [
            "<!DOCTYPE html>",
            "<html><head><title>Config History Export</title></head><body>",
            "<h1>Configuration History Export</h1>",
            f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
            "<table border='1' style='border-collapse: collapse;'>"
        ]
        
        # Заголовки таблицы
        headers = list(data[0].keys())
        header_row = "<tr>" + "".join(f"<th>{html.escape(str(h))}</th>" for h in headers) + "</tr>"
        html_lines.append(header_row)
        
        # Строки данных
        for record in data:
            row = "<tr>"
            for header in headers:
                value = record.get(header, '')
                # Ограничиваем длину отображаемого значения
                if isinstance(value, str) and len(value) > 100:
                    value = value[:100] + "..."
                row += f"<td>{html.escape(str(value))}</td>"
            row += "</tr>"
            html_lines.append(row)
        
        html_lines.extend(["</table>", "</body></html>"])
        return '\n'.join(html_lines)
    
    def _export_json(self, data, file_path):
        """Экспорт в JSON формат"""
        export_data = {
            'export_info': {
                'format': 'JSON',
                'exported_at': datetime.now().isoformat(),
                'total_records': len(data),
                'export_params': self._get_export_params()
            },
            'data': data
        }
        
        indent = 2 if self.pretty_format_check.isChecked() else None
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=indent, ensure_ascii=False, default=str)
    
    def _export_csv(self, data, file_path):
        """Экспорт в CSV формат"""
        if not data:
            return
        
        # Получаем все уникальные ключи из всех записей
        all_keys = set()
        for record in data:
            all_keys.update(record.keys())
        
        headers = sorted(list(all_keys))
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for record in data:
                # Заполняем отсутствующие ключи пустыми значениями
                row = {key: record.get(key, '') for key in headers}
                writer.writerow(row)
    
    def _export_html(self, data, file_path):
        """Экспорт в HTML формат"""
        html_content = self._format_as_html(data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
