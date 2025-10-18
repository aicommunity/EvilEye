"""
Dialogs module for EvilEye GUI

Модуль содержит диалоговые окна для GUI приложения.
"""

from .save_confirmation_dialog import SaveConfirmationDialog, SaveAsDialog
from .config_restore_dialog import ConfigRestoreDialog
from .config_compare_dialog import ConfigCompareDialog
from .job_details_dialog import JobDetailsDialog
from .export_history_dialog import ExportHistoryDialog
from .class_mapping_dialog import ClassMappingDialog

__all__ = [
    'SaveConfirmationDialog',
    'SaveAsDialog',
    'ConfigRestoreDialog',
    'ConfigCompareDialog',
    'JobDetailsDialog',
    'ExportHistoryDialog',
    'ClassMappingDialog'
]
