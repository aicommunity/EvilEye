import os
import json
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton
)
from capture.video_capture_base import CaptureDeviceType
from capture.video_capture import VideoCapture


def process_src_params(form_layouts, widgets_params_dict) -> list[dict]:
    if not form_layouts or widgets_params_dict is None:
        return []
    params = []
    param_name = ''
    for form_layout in form_layouts:
        src_params = {}
        widgets = (form_layout.itemAt(i).widget() for i in range(1, form_layout.count()))
        for widget in widgets:
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict:
                    param_name = widgets_params_dict[widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'camera':
                        src_params[param_name] = widget.text()
                    case 'source':
                        text = widget.currentText()
                        src_params[param_name] = CaptureDeviceType[text].value
                    case 'apiPreference':
                        text = widget.currentText()
                        src_params[param_name] = VideoCapture.VideoCaptureAPIs[text].name
                    case 'split':
                        src_params[param_name] = True if widget.isChecked() else False
                    case 'num_split':
                        src_params[param_name] = _process_numeric_types(widget.text())
                    case 'src_coords':
                        src_params[param_name] = _process_numeric_lists(widget.text())
                    case 'source_ids':
                        src_params[param_name] = _process_numeric_lists(widget.text())
                    case 'source_names':
                        src_params[param_name] = _process_str_list(widget.text())
        params.append(src_params)
    return params


def process_detector_params(form_layouts, widgets_params_dict):
    params = []
    param_name = ''
    for form_layout in form_layouts:
        src_params = {}
        widgets = (form_layout.itemAt(i).widget() for i in range(1, form_layout.count()))
        for widget in widgets:
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict:
                    param_name = widgets_params_dict[widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'source_ids':
                        src_params[param_name] = _process_numeric_lists(widget.text())
                    case 'model':
                        src_params[param_name] = widget.text()
                    case 'inference_size':
                        src_params[param_name] = _process_numeric_types(widget.text())
                    case 'conf':
                        src_params[param_name] = _process_numeric_types(widget.text())
                    case 'classes':
                        src_params[param_name] = _process_numeric_lists(widget.text())
                    case 'num_detection_threads':
                        src_params[param_name] = _process_numeric_types(widget.text())
                    case 'roi':
                        src_params[param_name] = _process_numeric_lists(widget.text())
        params.append(src_params)
    return params


def process_tracker_params(form_layouts, widgets_params_dict):
    params = []
    param_name = ''
    for form_layout in form_layouts:
        src_params = {}
        widgets = (form_layout.itemAt(i).widget() for i in range(1, form_layout.count()))
        for widget in widgets:
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict:
                    param_name = widgets_params_dict[widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'source_ids':
                        src_params[param_name] = _process_numeric_lists(widget.text())
                    case 'fps':
                        src_params[param_name] = _process_numeric_types(widget.text())
        params.append(src_params)
    return params


def process_visualizer_params(form_layouts, widgets_params_dict):
    params = {}
    param_name = ''
    for form_layout in form_layouts:
        widgets = (form_layout.itemAt(i).widget() for i in range(1, form_layout.count()))
        for widget in widgets:
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict:
                    param_name = widgets_params_dict[widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'num_width':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'num_height':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'visual_buffer_num_frames':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'source_ids':
                        params[param_name] = _process_numeric_lists(widget.text())
                    case 'fps':
                        params[param_name] = _process_numeric_lists(widget.text())
                    case 'gui_enabled':
                        params[param_name] = True if widget.isChecked() else False
                    case 'show_debug_info':
                        params[param_name] = True if widget.isChecked() else False
                    case 'objects_journal_enabled':
                        params[param_name] = True if widget.isChecked() else False
    return params


def process_database_params(form_layouts, widgets_params_dict):
    params = {}
    param_name = ''
    for form_layout in form_layouts:
        widgets = (form_layout.itemAt(i).widget() for i in range(1, form_layout.count()))
        for widget in widgets:
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict:
                    param_name = widgets_params_dict[widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'user_name':
                        params[param_name] = widget.text()
                    case 'password':
                        params[param_name] = widget.text()
                    case 'database_name':
                        params[param_name] = widget.text()
                    case 'host_name':
                        params[param_name] = widget.text()
                    case 'port':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'default_database_name':
                        params[param_name] = widget.text()
                    case 'default_password':
                        params[param_name] = widget.text()
                    case 'default_user_name':
                        params[param_name] = widget.text()
                    case 'default_host_name':
                        params[param_name] = widget.text()
                    case 'default_port':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'create_new_project':
                        params[param_name] = True if widget.isChecked() else False
                    case 'image_dir':
                        params[param_name] = widget.text()
                    case 'preview_width':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'preview_height':
                        params[param_name] = _process_numeric_types(widget.text())
    return params


def process_events_params(form_layouts, widgets_params_dict):
    params = {}
    param_name = ''
    for form_layout in form_layouts:
        widgets = [form_layout.itemAt(i).widget() for i in range(1, form_layout.count())]
        detector_name = form_layout.itemAt(0).widget().text()
        params[detector_name] = {}
        for i, widget in enumerate(widgets):
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict[detector_name]:
                    param_name = widgets_params_dict[detector_name][widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'event_threshold':
                        params[detector_name][param_name] = _process_numeric_types(widget.text())
                    case 'zone_left_threshold':
                        params[detector_name][param_name] = _process_numeric_types(widget.text())
                    case 'sources':
                        params[detector_name][param_name] = _process_events_src_params(widgets[i-1:])
                        break
    return params


def process_handler_params(form_layouts, widgets_params_dict):
    params = {}
    param_name = ''
    for form_layout in form_layouts:
        widgets = (form_layout.itemAt(i).widget() for i in range(1, form_layout.count()))
        for widget in widgets:
            if isinstance(widget, QLabel):
                if widget.text() in widgets_params_dict:
                    param_name = widgets_params_dict[widget.text()]
                else:
                    param_name = ''
            else:
                if not param_name:
                    continue
                match param_name:
                    case 'history_len':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'lost_store_time_secs':
                        params[param_name] = _process_numeric_types(widget.text())
                    case 'lost_thresh':
                        params[param_name] = _process_numeric_types(widget.text())
    return params


def _process_numeric_types(string: str):
    if not string:
        return ''
    try:
        result = json.loads(string)
    except json.JSONDecodeError as err:
        raise ValueError(f'Given string: {string} - does not match the specified pattern') from err
    return result


def _process_numeric_lists(string: str):
    return _process_numeric_types(string)


def _process_str_list(string: str) -> list[str]:
    string = string.strip('[] ')
    string = string.replace(']', '')
    string = string.replace('[', '')
    return string.split(', ')


def _process_events_src_params(widgets: list) -> dict:
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
                    src_params[last_src_id] = _process_numeric_lists(widget.text())
                case 'Time':
                    src_params[last_src_id] = _process_str_list(widget.text())
    return src_params


if __name__ == '__main__':
    s = ''
    s2 = '[[15:30:30, 16:00:00], [15:30:30, 16:00:00]]'
    print(_process_str_list(s), _process_str_list(s))
