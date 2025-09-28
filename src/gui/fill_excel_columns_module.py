"""
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog
)
from PySide6.QtCore import Qt  # QMimeData
# from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPalette


class FillExcelColumns(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Drag and Drop Files")
        self.setGeometry(100, 100, 400, 300)

        self.widget_ui()

    def widget_ui(self):
        main_layout = QVBoxLayout()

        self.label = QLabel("Drag and drop files here \n or \n", alignment=Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: 2px dashed gray; padding: 20px;")
        self.label.setAcceptDrops(True)
        self.label.dragEnterEvent = self.drag_enter_event
        self.label.dropEvent = self.drop_event

        browse_file_button = QPushButton("Browse file")
        browse_file_button.clicked.connect(self.browse_file)

        main_layout.addWidget(self.label)
        main_layout.addWidget(browse_file_button)

        self.setLayout(main_layout)

    def drag_enter_event(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def drop_event(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            print(f"File dropped: {file_path}")

    def browse_file(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select files", "", "Excel-files (*.xlsx; *.xls)")
        for file_path in file_paths:
            print(f"File selected: {file_path}")
