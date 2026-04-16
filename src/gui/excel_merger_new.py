import re
import sys
import pandas as pd
import traceback
from itertools import permutations
from pathlib import Path
from openpyxl import load_workbook

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QComboBox,
    QScrollArea, QTabWidget, QLineEdit, QFrame
)
from PySide6.QtCore import Qt

PHONE_CLEAN_PATTERN = re.compile(r'\D')


def _format_phone_number(number: str) -> str:
    """Функция, которая очищает телефонный номер от лишних символов и приводит его к формату +7XXXXXXXXXX."""
    cleaned_phone_number = PHONE_CLEAN_PATTERN.sub("", number)

    if len(cleaned_phone_number) == 11 and cleaned_phone_number.startswith(("7", "8")):
        return "+7" + cleaned_phone_number[1:]

    if len(cleaned_phone_number) == 10:
        return "+7" + cleaned_phone_number

    return ""


def _process_cell_data(cell_value) -> list[str]:
    """Функция, которая обрабатывает содержимое одной ячейки."""
    if pd.isna(cell_value):
        return []

    cell_value_string = str(cell_value).strip().lower()
    if cell_value_string in ("nan", "none", ""):
        return []

    processed_numbers = []
    split_numbers = re.split(r'[;,]+', cell_value_string)
    for number in split_numbers:
        formatted_number = _format_phone_number(number)
        if formatted_number:
            processed_numbers.append(formatted_number)

    return processed_numbers


def process_data(series: pd.Series) -> pd.Series:
    """Функция, которая очищает и форматирует поля с телефонными номерами и прочие поля."""
    return series.apply(_process_cell_data)


def generate_fio_variants(fio) -> list[str]:
    """Функция, которая генерирует различные возможные перестановки ФИО для последующего гибкого сравнения."""
    if pd.isna(fio) or not isinstance(fio, str):
        return []

    normalized_fio = fio.strip().lower().replace("ё", "е")
    if not normalized_fio:
        return []

    fio_parts = normalized_fio.split()
    fio_parts = fio_parts[:4]

    fio_variants = set()
    for permutation_length in range(1, len(fio_parts) + 1):
        for fio_combination in permutations(fio_parts, permutation_length):
            fio_variants.add(" ".join(fio_combination))

    return list(fio_variants)


# def process_data(series):
#     """Очистка и форматирование телефонных и прочих полей"""
#     return series.apply(
#         lambda x: x.strip().lower() if isinstance(x, str) else str(x).strip().lower()
#     ).apply(
#         lambda x: [
#             num.strip().replace('8', '+7', 1).replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
#             if num.strip().startswith('8') else
#             "+7" + num.strip()[1:].replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
#             if num.strip().startswith('7') else num.strip().replace(' ', '').replace('(', '').replace(')', '').replace('-', '')
#             for num in x.split(';') if isinstance(x, str) and len(num.strip()) > 5 and '_' not in num
#         ] if isinstance(x, str) and x.lower() != 'nan' else []
#     )


# def generate_fio_variants(fio):
#     """Генерация перестановок ФИО для гибкого сравнения"""
#     variants = set()
#     if not isinstance(fio, str) or pd.isna(fio):
#         return []

#     fio_norm = fio.strip().lower().replace('ё', 'е')
#     parts = fio_norm.split()

#     if len(parts) == 1:
#         variants.add(fio_norm)
#     elif len(parts) == 2:
#         variants.add(parts[0] + ' ' + parts[1])
#         variants.add(parts[1] + ' ' + parts[0])
#     elif len(parts) == 3:
#         variants.add(parts[0] + ' ' + parts[1])
#         variants.add(parts[0] + ' ' + parts[2])
#         variants.add(parts[2] + ' ' + parts[1] + ' ' + parts[0])
#         variants.add(parts[2] + ' ' + parts[0] + ' ' + parts[1])
#         variants.add(parts[1] + ' ' + parts[0] + ' ' + parts[2])
#         variants.add(parts[1] + ' ' + parts[2] + ' ' + parts[0])
#         variants.add(parts[0] + ' ' + parts[2] + ' ' + parts[1])

#     variants.add(' '.join(parts))
#     return list(variants)


def merge_excel(df1, df2, common_fields):
    """Объединение DataFrame с использованием логики ФИО и списков"""
    merged_all = []

    for field1, field2 in common_fields:
        df1_copy = df1.copy().reset_index(drop=False).rename(columns={'index': '_idx1'})
        df2_copy = df2.copy().reset_index(drop=False).rename(columns={'index': '_idx2'})

        # Эвристика: если в названии столбца есть 'фио', используем генератор вариантов
        if 'фио' in field1.lower() and 'фио' in field2.lower():
            df1_copy['join_key'] = df1_copy[field1].fillna('').apply(generate_fio_variants)
            df2_copy['join_key'] = df2_copy[field2].fillna('').apply(generate_fio_variants)
        else:
            df1_copy['join_key'] = process_data(df1_copy[field1])
            df2_copy['join_key'] = process_data(df2_copy[field2])

        # Раскрываем списки ключей в отдельные строки
        temp1 = df1_copy.explode('join_key')
        temp2 = df2_copy.explode('join_key')

        # Убираем пустые ключи
        temp1 = temp1[temp1['join_key'].notna() & (temp1['join_key'] != '')]
        temp2 = temp2[temp2['join_key'].notna() & (temp2['join_key'] != '')]

        # Объединяем
        merged = pd.merge(temp1, temp2, on='join_key', how='inner', suffixes=('_1', '_2'))

        # Удаляем дубликаты в рамках текущей пары объединения
        merged = merged.drop_duplicates(subset=['_idx1', '_idx2'])
        merged_all.append(merged)

    if not merged_all:
        return pd.DataFrame()

    # Конкатенируем результаты по всем парам и удаляем глобальные дубликаты
    result = pd.concat(merged_all, ignore_index=True)
    result = result.drop_duplicates(subset=['_idx1', '_idx2'])

    return result


# Паттерн удаляет: [, ], ', "
PATTERN = re.compile(r"[\[\]\"']")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Очистка строковых столбцов от лишних символов"""
    obj_cols = df.select_dtypes(include=["object", "string"]).columns
    if len(obj_cols) == 0:
        return df

    df[obj_cols] = df[obj_cols].apply(
        lambda col: col.astype("string").str.replace(PATTERN, "", regex=True)
    )
    return df


class MergerTab(QWidget):
    """Вкладка для объединения файлов"""
    def __init__(self):
        super().__init__()
        self.file1 = ""
        self.file2 = ""
        self.columns_file1 = []
        self.columns_file2 = []
        self.common_fields = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Блок загрузки файлов
        btn1 = QPushButton("📁 Загрузить первый файл")
        btn1.clicked.connect(self.load_file1)
        self.file1_label = QLabel("Файл не выбран")
        self.file1_label.setStyleSheet("color: #666;")

        btn2 = QPushButton("📁 Загрузить второй файл")
        btn2.clicked.connect(self.load_file2)
        self.file2_label = QLabel("Файл не выбран")
        self.file2_label.setStyleSheet("color: #666;")

        layout.addWidget(btn1)
        layout.addWidget(self.file1_label)
        layout.addWidget(btn2)
        layout.addWidget(self.file2_label)

        # Разделитель
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Область пар столбцов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.pair_widget = QWidget()
        self.pair_layout = QVBoxLayout(self.pair_widget)
        self.pair_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.pair_widget)
        layout.addWidget(scroll)

        # Кнопки управления
        btn_add = QPushButton("➕ Добавить пару столбцов")
        btn_add.clicked.connect(self.add_column_pair)

        btn_merge = QPushButton("🔗 Объединить файлы")
        btn_merge.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        btn_merge.clicked.connect(self.merge)

        layout.addWidget(btn_add)
        layout.addWidget(btn_merge)

    def load_file1(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите первый файл", "", "Excel (*.xlsx *.xls)")
        if path:
            self.file1 = path
            self.file1_label.setText(f"✅ {Path(path).name}")
            self.columns_file1 = pd.read_excel(path, nrows=0).columns.tolist()
            for cb1, _ in self.common_fields:
                cb1.clear()
                cb1.addItems(self.columns_file1)

    def load_file2(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите второй файл", "", "Excel (*.xlsx *.xls)")
        if path:
            self.file2 = path
            self.file2_label.setText(f"✅ {Path(path).name}")
            self.columns_file2 = pd.read_excel(path, nrows=0).columns.tolist()
            for _, cb2 in self.common_fields:
                cb2.clear()
                cb2.addItems(self.columns_file2)

    def add_column_pair(self):
        if not self.columns_file1 or not self.columns_file2:
            QMessageBox.warning(self, "Внимание", "Сначала загрузите оба файла!")
            return

        frame = QWidget()
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        cb1 = QComboBox()
        cb1.addItems(self.columns_file1)

        cb2 = QComboBox()
        cb2.addItems(self.columns_file2)

        btn_remove = QPushButton("❌")
        btn_remove.setFixedWidth(40)
        btn_remove.clicked.connect(lambda: self.remove_pair(frame, cb1, cb2))

        frame_layout.addWidget(QLabel("Файл 1:"))
        frame_layout.addWidget(cb1, 1)
        frame_layout.addWidget(QLabel("Файл 2:"))
        frame_layout.addWidget(cb2, 1)
        frame_layout.addWidget(btn_remove)

        self.pair_layout.addWidget(frame)
        self.common_fields.append((cb1, cb2))

    def remove_pair(self, frame, cb1, cb2):
        self.common_fields = [(c1, c2) for c1, c2 in self.common_fields if c1 != cb1 and c2 != cb2]
        frame.deleteLater()

    def merge(self):
        if not self.file1 or not self.file2:
            QMessageBox.warning(self, "Ошибка", "Загрузите оба файла.")
            return

        pairs = [(cb1.currentText(), cb2.currentText()) for cb1, cb2 in self.common_fields]
        if not pairs:
            QMessageBox.warning(self, "Ошибка", "Добавьте хотя бы одну пару столбцов.")
            return

        try:
            df1 = pd.read_excel(self.file1)
            df2 = pd.read_excel(self.file2)
            merged_df = merge_excel(df1, df2, pairs)

            if merged_df.empty:
                QMessageBox.information(self, "Результат", "Совпадений не найдено.")
                return

            # if 'ФИО_1' in merged_df.columns:
            #     merged_df = merged_df.sort_values(by='ФИО_1').reset_index(drop=True)
            merged_df = merged_df.sort_values(by="Личный номер дела").reset_index(drop=True)

            unique_count = merged_df['_idx1'].nunique() if '_idx1' in merged_df.columns else 0

            # Удаляем системные колонки
            cols_to_drop = [col for col in ['join_key', '_idx1', '_idx2'] if col in merged_df.columns]
            merged_df.drop(columns=cols_to_drop, inplace=True)

            save_path, _ = QFileDialog.getSaveFileName(self, "Сохранить", "merged_output.xlsx", "Excel (*.xlsx)")
            if not save_path:
                return

            merged_df.to_excel(save_path, index=False)

            # Форматирование ширины (отложенное открытие через openpyxl)
            wb = load_workbook(save_path)
            ws = wb.active
            for col in ws.columns:
                max_len = max((len(str(cell.value)) for cell in col if cell.value), default=0)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 5, 50)
            wb.save(save_path)
            wb.close()

            QMessageBox.information(self, "Успех", f"Успешно объединено!\nУникальных записей (Файл 1): {unique_count}")

        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Ошибка", f"Произошла ошибка при объединении:\n{str(e)}")


class CleanerTab(QWidget):
    """Вкладка для очистки файла"""
    def __init__(self):
        super().__init__()
        self.file_path = ""
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel('Удаление символов: [ ] " \' из всех текстовых ячеек')
        info_label.setStyleSheet("font-style: italic; color: #555;")
        layout.addWidget(info_label)

        file_layout = QHBoxLayout()
        self.path_entry = QLineEdit()
        self.path_entry.setReadOnly(True)
        self.path_entry.setPlaceholderText("Файл не выбран...")

        btn_select = QPushButton("Выбрать файл")
        btn_select.clicked.connect(self.select_file)

        file_layout.addWidget(self.path_entry)
        file_layout.addWidget(btn_select)
        layout.addLayout(file_layout)

        self.btn_process = QPushButton("✨ Очистить и сохранить")
        self.btn_process.setStyleSheet("background-color: #2196F3; color: white; padding: 10px; font-weight: bold;")
        self.btn_process.clicked.connect(self.process)
        layout.addWidget(self.btn_process)

        layout.addStretch()

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите Excel-файл", "", "Excel (*.xlsx *.xls)")
        if path:
            self.file_path = path
            self.path_entry.setText(path)

    def process(self):
        if not self.file_path:
            QMessageBox.warning(self, "Ошибка", "Выберите файл для очистки.")
            return

        try:
            self.btn_process.setText("Обработка...")
            QApplication.processEvents()  # Обновляем UI

            # Читаем все листы
            sheets = pd.read_excel(self.file_path, sheet_name=None, dtype=object)
            cleaned_sheets = {name: clean_dataframe(df) for name, df in sheets.items()}

            # Предлагаем куда сохранить (по умолчанию добавляем _cleaned к имени)
            default_out = Path(self.file_path).with_name(f"{Path(self.file_path).stem}_cleaned.xlsx")
            save_path, _ = QFileDialog.getSaveFileName(self, "Сохранить очищенный файл", str(default_out), "Excel (*.xlsx)")

            if not save_path:
                self.btn_process.setText("✨ Очистить и сохранить")
                return

            with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
                for name, df in cleaned_sheets.items():
                    df.to_excel(writer, sheet_name=name, index=False)

            self.btn_process.setText("✨ Очистить и сохранить")
            QMessageBox.information(self, "Успех", f"Файл очищен и сохранен:\n{save_path}")

        except Exception as e:
            self.btn_process.setText("✨ Очистить и сохранить")
            traceback.print_exc()
            QMessageBox.critical(self, "Ошибка", f"Ошибка при очистке файла:\n{str(e)}")


class MainWindow(QMainWindow):
    """Главное окно приложения"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Excel Tools Pro")
        self.resize(600, 500)

        # Создаем вкладки
        tabs = QTabWidget()
        tabs.addTab(MergerTab(), "🔗 Объединение файлов")
        tabs.addTab(CleanerTab(), "🧹 Очистка данных")

        self.setCentralWidget(tabs)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Небольшая стилизация для современного вида
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
