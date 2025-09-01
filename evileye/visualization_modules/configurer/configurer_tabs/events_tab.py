import copy
try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QHBoxLayout, QLineEdit,
        QSizePolicy, QFormLayout, QPushButton, QSpacerItem
    )
    from PyQt6.QtCore import pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QHBoxLayout, QLineEdit,
        QSizePolicy, QFormLayout, QPushButton, QSpacerItem
    )
    from PyQt5.QtCore import pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
from evileye.visualization_modules.configurer import parameters_processing


class EventsTab(QWidget):
    def __init__(self, config_params):
        super().__init__()

        self.params = config_params
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.sources_counter = 0
        self.layouts_counter = 0

        # Словарь для сопоставления полей интерфейса с полями json-файла
        self.line_edit_param = {"ZoneEventsDetector": {}, "FieldOfViewEventsDetector": {}}
        self._setup_events_layout()

    def _setup_events_layout(self):
        zone_event_layout = self._setup_zone_detector_form()
        fov_event_layout = self._setup_fov_detector_form()
        h_layout = QHBoxLayout()
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hor_layouts.append(h_layout)
        # self.vertical_layout.addLayout(h_layout)
        h_layout.addLayout(zone_event_layout)
        h_layout.addItem(QSpacerItem(50, 10))
        h_layout.addLayout(fov_event_layout)
        self.setLayout(h_layout)

    def _setup_zone_detector_form(self):
        self.form_layout = QFormLayout()
        self.form_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name = QLabel('ZoneEventsDetector')
        self.form_layout.addWidget(name)

        event_threshold = QLineEdit()
        self.form_layout.addRow('Event threshold', event_threshold)
        self.line_edit_param['ZoneEventsDetector']['Event threshold'] = 'event_threshold'

        zone_left_threshold = QLineEdit()
        self.form_layout.addRow('Zone left threshold', zone_left_threshold)
        self.line_edit_param['ZoneEventsDetector']['Zone left threshold'] = 'zone_left_threshold'

        new_src = QPushButton('New source')
        new_src.clicked.connect(self._add_source)
        self.form_layout.addRow('Add a source', new_src)

        sources_label = QLabel('Sources')
        self.form_layout.addWidget(sources_label)

        widgets = (self.form_layout.itemAt(i).widget() for i in range(self.form_layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)
        self.widgets_counter += 1
        return self.form_layout

    def _setup_fov_detector_form(self):
        self.fov_form_layout = QFormLayout()
        self.fov_form_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name = QLabel('FieldOfViewEventsDetector')
        self.fov_form_layout.addWidget(name)

        new_src = QPushButton('New source')
        new_src.clicked.connect(self._add_source_fov)
        self.fov_form_layout.addRow('Add a source', new_src)

        sources_label = QLabel('Sources')
        self.fov_form_layout.addWidget(sources_label)

        widgets = (self.fov_form_layout.itemAt(i).widget() for i in range(self.fov_form_layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)
        self.widgets_counter += 1
        return self.fov_form_layout

    @pyqtSlot()
    def _add_source(self):
        src_id = QLineEdit()
        self.form_layout.addRow(f'Source id', src_id)
        src_id.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        src_id.setMinimumWidth(200)
        self.line_edit_param['ZoneEventsDetector']['Source id'] = 'sources'

        zone_coords = QLineEdit()
        zone_coords.setText('[[zone_coords1], [zone_coords2]]')
        self.form_layout.addRow('Zones', zone_coords)
        zone_coords.setMinimumWidth(200)
        zone_coords.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    @pyqtSlot()
    def _add_source_fov(self):
        src_id = QLineEdit()
        self.fov_form_layout.addRow(f'Source id', src_id)
        src_id.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        src_id.setMinimumWidth(200)
        self.line_edit_param['FieldOfViewEventsDetector']['Source id'] = 'sources'

        time = QLineEdit()
        time.setText('[[HH:MM:SS, HH:MM:SS]]')
        self.fov_form_layout.addRow('Time', time)
        time.setMinimumWidth(200)
        time.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def get_forms(self) -> list[QFormLayout]:
        form_layouts = []
        for h_layout in self.hor_layouts:
            forms = [form for i in range(h_layout.count()) if isinstance(form := h_layout.itemAt(i), QFormLayout)]
            form_layouts.extend(forms)
        return form_layouts

    def get_params(self):
        form_layouts = self.get_forms()
        events_params = self._get_events_params(form_layouts)
        return events_params

    def _get_events_params(self, form_layouts):
        ev_params = {}
        param_name = ''
        for form_layout in form_layouts:
            widgets = [form_layout.itemAt(i).widget() for i in range(1, form_layout.count())]
            detector_name = form_layout.itemAt(0).widget().text()
            ev_params[detector_name] = {}
            for i, widget in enumerate(widgets):
                if isinstance(widget, QLabel):
                    if widget.text() in self.line_edit_param[detector_name]:
                        param_name = self.line_edit_param[detector_name][widget.text()]
                    else:
                        param_name = ''
                else:
                    if not param_name:
                        continue
                    match param_name:
                        case 'event_threshold':
                            ev_params[detector_name][param_name] = parameters_processing.process_numeric_types(widget.text())
                        case 'zone_left_threshold':
                            ev_params[detector_name][param_name] = parameters_processing.process_numeric_types(widget.text())
                        case 'sources':
                            ev_params[detector_name][param_name] = self._get_events_src_params(widgets[i - 1:])
                            break
        return ev_params

    def _get_events_src_params(self, widgets: list) -> dict:
        src_params = {}
        param_name = ''
        last_src_id = ''
        for widget in widgets:
            if isinstance(widget, QLabel):
                param_name = widget.text()
            else:
                match param_name:
                    case 'Source id':
                        last_src_id = widget.text()
                    case 'Zones':
                        src_params[last_src_id] = parameters_processing.process_numeric_lists(widget.text())
                    case 'Time':
                        src_params[last_src_id] = parameters_processing.process_str_list(widget.text())
        return src_params
