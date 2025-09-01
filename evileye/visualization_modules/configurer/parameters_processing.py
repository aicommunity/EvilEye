import os
import json
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton
)
from ...capture.video_capture_base import CaptureDeviceType
from ...capture.video_capture import VideoCapture


def process_numeric_types(string: str):
    if not string:
        return ''
    try:
        result = json.loads(string)
    except json.JSONDecodeError as err:
        raise ValueError(f'Given string: {string} - does not match the specified pattern') from err
    return result


def process_numeric_lists(string: str):
    return process_numeric_types(string)


def process_str_list(string: str) -> list[str]:
    string = string.strip('[] ')
    string = string.replace(']', '')
    string = string.replace('[', '')
    return string.split(', ')


def process_events_src_params(widgets: list) -> dict:
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
                    src_params[last_src_id] = process_numeric_lists(widget.text())
                case 'Time':
                    src_params[last_src_id] = process_str_list(widget.text())
    return src_params


if __name__ == '__main__':
    s = ''
    s2 = '[[15:30:30, 16:00:00], [15:30:30, 16:00:00]]'
    print(process_str_list(s), process_str_list(s))
