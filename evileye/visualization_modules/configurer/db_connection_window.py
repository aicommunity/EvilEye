from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QDateTimeEdit, QHeaderView, QLineEdit, QTableView, QStyledItemDelegate,
    QMessageBox, QTextEdit, QFormLayout, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
from . import parameters_processing
from PyQt6.QtSql import QSqlDatabase


class DatabaseConnectionWindow(QWidget):
    database_connection_signal = pyqtSignal()

    def __init__(self, database_access_params, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Database configurer')
        self.setMinimumSize(300, 150)
        self.main_layout = QVBoxLayout()
        self.db_layout = QFormLayout()
        self.connect_button = QPushButton('Connect')
        self.db_params = database_access_params['database']
        self.line_edit_param = {'Username': self.db_params['user_name'], 'Password': self.db_params['password'],
                                'DB name': self.db_params['database_name'], 'Host name': self.db_params['host_name'],
                                'Port': self.db_params['port']}

        self.is_conn = False

        self._setup_db_form()
        self.connect_button.clicked.connect(self._save_db_params)

        self.main_layout.addLayout(self.db_layout)
        self.main_layout.addWidget(self.connect_button)
        self.setLayout(self.main_layout)

    def _setup_db_form(self):
        name = QLabel('Database Parameters')
        self.db_layout.addWidget(name)

        user_name = QLineEdit()
        self.db_layout.addRow('Username', user_name)
        self.line_edit_param['Username'] = 'user_name'
        user_name.setText(self.db_params['user_name'])

        password = QLineEdit()
        self.db_layout.addRow('Password', password)
        self.line_edit_param['Password'] = 'password'
        password.setText(self.db_params['password'])

        db_name = QLineEdit()
        self.db_layout.addRow('DB name', db_name)
        self.line_edit_param['DB name'] = 'database_name'
        db_name.setText(self.db_params['database_name'])

        host_name = QLineEdit()
        self.db_layout.addRow('Host name', host_name)
        self.line_edit_param['Host name'] = 'host_name'
        host_name.setText(self.db_params['host_name'])

        port = QLineEdit()
        self.db_layout.addRow('Port', port)
        self.line_edit_param['Port'] = 'port'
        port.setText(str(self.db_params['port']))

        widgets = (self.db_layout.itemAt(i).widget() for i in range(self.db_layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)

    def _save_db_params(self):
        params = configurer.parameters_processing.process_database_params([self.db_layout], self.line_edit_param)
        self.db_params = params
        self._connect_to_db()
        if self.is_connected():
            self.database_connection_signal.emit()
            self.hide()

    def _connect_to_db(self):
        db = QSqlDatabase.addDatabase("QPSQL", 'jobs_conn')
        db.setHostName(self.db_params['host_name'])
        db.setDatabaseName(self.db_params['database_name'])
        db.setUserName(self.db_params['user_name'])
        db.setPassword(self.db_params['password'])
        db.setPort(self.db_params['port'])
        if not db.open():
            QMessageBox.critical(
                None,
                "Connection error",
                str(db.lastError().text()),
            )
            self.is_conn = False
        else:
            self.is_conn = True

    def closeEvent(self, event) -> None:
        print('DB jobs_conn removed')
        QSqlDatabase.removeDatabase('jobs_conn')
        event.accept()

    def is_connected(self) -> bool:
        return self.is_conn
