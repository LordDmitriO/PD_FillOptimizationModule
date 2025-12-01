from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QCheckBox, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QCoreApplication, QSettings


class SettingsWindow(QDialog):
    def __init__(self, parent=None, is_dev_mode=False):
        super().__init__(parent)

        self.setWindowTitle("Настройки")
        self.setFixedSize(300, 150)

        QCoreApplication.setOrganizationName("MosPolyProgPD")
        QCoreApplication.setApplicationName("FillOptimizationModule")
        self.settings = QSettings(QSettings.Scope.UserScope)
        self.settings.setDefaultFormat(QSettings.Format.NativeFormat)

        self.setting_window_ui(is_dev_mode)

    def setting_window_ui(self, is_dev_mode):
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.dev_mode_checkbox = QCheckBox("Режим разработчика")
        self.dev_mode_checkbox.setAccessibleIdentifier("dev_mode")
        self.dev_mode_checkbox.setChecked(is_dev_mode)
        self.dev_mode_checkbox.checkStateChanged.connect(self.onCheckboxChange)

        self.layout.addWidget(self.dev_mode_checkbox)
        self.layout.addStretch()

        self.create_buttons()

    def onCheckboxChange(self, current_checkbox_state):
        if current_checkbox_state == Qt.CheckState.Checked:
            print("Режим разработчика включен")
        else:
            print("Режим разработчика выключен")

    def create_buttons(self):
        """Создание кнопок в нижней части окна"""
        button_layout = QHBoxLayout()

        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self.on_save_clicked)

        self.ok_button = QPushButton("ОК")
        self.ok_button.clicked.connect(self.on_ok_clicked)

        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.ok_button)

        self.layout.addLayout(button_layout)

    def get_current_settings(self):
        current_settings = {}
        items_count = self.layout.count()
        for i in range(0, items_count):
            current_widget = self.layout.itemAt(i).widget()
            if current_widget:
                if self.layout.itemAt(i).widget().__class__.__name__ == "QCheckBox":
                    current_settings[self.layout.itemAt(i).widget().accessibleIdentifier()] = self.layout.itemAt(i).widget().isChecked()

        return current_settings

    def on_save_clicked(self):
        """Логика кнопки Сохранить"""
        current_settings = self.get_current_settings()

        self.settings.setValue("dev_mode", current_settings["dev_mode"])

        print("Настройки сохранены")

    def on_ok_clicked(self):
        """Логика кнопки ОК: проверка на изменения"""
        current_settings = self.get_current_settings()

        if current_settings["dev_mode"] == self.settings.value("dev_mode", type=bool):
            self.accept()

            return

        message = QMessageBox(self)
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle("Несохраненные изменения")
        message.setText("Настройки были изменены.")
        message.setInformativeText("Сохранить изменения перед выходом?")

        button_save = message.addButton("Сохранить", QMessageBox.ButtonRole.AcceptRole)
        button_discard = message.addButton("Не сохранять", QMessageBox.ButtonRole.DestructiveRole)
        button_cancel = message.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)

        message.exec()

        if message.clickedButton() == button_save:
            self.on_save_clicked()
            self.accept()
        elif message.clickedButton() == button_discard:
            self.reject()
        else:
            pass


def run_settings_dialog(parent, current_dev_mode):
    dialog = SettingsWindow(parent, is_dev_mode=current_dev_mode)
    dialog.exec()
    current_dev_mode = dialog.settings.value("dev_mode", type=bool)

    return {"dev_mode": current_dev_mode}
