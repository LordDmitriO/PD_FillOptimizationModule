"""
Модуль для объединения Excel файлов по указанным столбцам
"""

import pandas as pd
import traceback
from openpyxl import load_workbook
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
    QComboBox,
    QScrollArea,
)

def merge_excel(df1, df2, pairs):
    """
    Объединение двух DataFrame по указанным парам столбцов
    
    Args:
        df1: Первый DataFrame
        df2: Второй DataFrame
        pairs: Список кортежей (col1, col2) для объединения
        
    Returns:
        Объединенный DataFrame
    """
    # Создаем копии для работы
    d1 = df1.copy().reset_index(drop=True)
    d2 = df2.copy().reset_index(drop=True)
    
    # Добавляем индексы для отслеживания исходных строк
    d1['_idx1'] = d1.index
    d2['_idx2'] = d2.index
    
    # Объединяем по первой паре столбцов
    col1, col2 = pairs[0]
    merged = d1.merge(
        d2,
        left_on=col1,
        right_on=col2,
        how='outer',
        suffixes=('_1', '_2')
    )
    
    # Объединяем по остальным парам, если есть
    for col1, col2 in pairs[1:]:
        # Создаем вспомогательный ключ для объединения
        merged['join_key'] = (
            merged[col1 + '_1'].astype(str).fillna('') + '_' + 
            merged[col2 + '_2'].astype(str).fillna('')
        )
        
        # Объединяем с дублирующимися записями
        temp_merge = d1.merge(
            d2,
            left_on=col1,
            right_on=col2,
            how='outer',
            suffixes=('_1', '_2')
        )
        temp_merge['join_key'] = (
            temp_merge[col1 + '_1'].astype(str).fillna('') + '_' + 
            temp_merge[col2 + '_2'].astype(str).fillna('')
        )
        
        # Объединяем результаты
        merged = pd.concat([merged, temp_merge]).drop_duplicates(subset=['join_key'], keep='first')
    
    return merged


class ExcelMerger(QWidget):
    """Виджет для объединения двух Excel файлов"""

    def __init__(self):
        super().__init__()
        self.file1 = ""
        self.file2 = ""
        self.columns_file1 = []
        self.columns_file2 = []
        self.common_fields = []  # Список кортежей (combobox1, combobox2)
        
        self.init_ui()

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Кнопка загрузки первого файла
        btn1 = QPushButton("📁 Загрузить первый файл")
        btn1.clicked.connect(self.load_file1)
        btn1.setStyleSheet("padding: 10px; font-size: 14px;")
        layout.addWidget(btn1)
        
        self.file1_label = QLabel("Файл не выбран")
        self.file1_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(self.file1_label)

        # Кнопка загрузки второго файла
        btn2 = QPushButton("📁 Загрузить второй файл")
        btn2.clicked.connect(self.load_file2)
        btn2.setStyleSheet("padding: 10px; font-size: 14px;")
        layout.addWidget(btn2)
        
        self.file2_label = QLabel("Файл не выбран")
        self.file2_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(self.file2_label)

        # Область для пар столбцов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        self.pair_widget = QWidget()
        self.pair_layout = QVBoxLayout()
        self.pair_widget.setLayout(self.pair_layout)
        scroll.setWidget(self.pair_widget)
        layout.addWidget(scroll)

        # Кнопка добавления пары
        btn_add = QPushButton("➕ Добавить пару столбцов для объединения")
        btn_add.clicked.connect(self.add_column_pair)
        btn_add.setStyleSheet("padding: 8px; font-size: 12px;")
        layout.addWidget(btn_add)

        # Кнопка объединения
        btn_merge = QPushButton("🔗 Объединить файлы")
        btn_merge.clicked.connect(self.merge)
        btn_merge.setStyleSheet(
            "padding: 12px; font-size: 16px; background-color: #4CAF50; color: white;"
        )
        layout.addWidget(btn_merge)
        
        layout.addStretch()

    def add_column_pair(self):
        """Добавление пары столбцов для объединения"""
        if not self.columns_file1 or not self.columns_file2:
            QMessageBox.warning(
                self, "Ошибка", "Сначала загрузите оба файла!"
            )
            return

        frame = QWidget()
        frame_layout = QHBoxLayout()
        frame.setLayout(frame_layout)

        cb1 = QComboBox()
        cb1.addItems(self.columns_file1)
        cb1.setEditable(False)
        
        cb2 = QComboBox()
        cb2.addItems(self.columns_file2)
        cb2.setEditable(False)

        btn_remove = QPushButton("❌ Удалить")
        btn_remove.clicked.connect(lambda: self.remove_pair(frame, cb1, cb2))
        btn_remove.setStyleSheet("padding: 5px;")

        frame_layout.addWidget(QLabel("Файл 1:"))
        frame_layout.addWidget(cb1)
        frame_layout.addWidget(QLabel("Файл 2:"))
        frame_layout.addWidget(cb2)
        frame_layout.addWidget(btn_remove)

        self.pair_layout.addWidget(frame)
        self.common_fields.append((cb1, cb2))

    def remove_pair(self, frame, cb1, cb2):
        """Удаление пары столбцов"""
        self.common_fields = [
            (c1, c2) for c1, c2 in self.common_fields if (c1, c2) != (cb1, cb2)
        ]
        frame.deleteLater()

    def load_file1(self):
        """Загрузка первого файла"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите первый файл", "", "Excel-файлы (*.xlsx *.xls)"
        )
        if path:
            try:
                self.file1 = path
                self.file1_label.setText(f"✅ {path}")
                cols = pd.read_excel(path).columns.tolist()
                self.columns_file1 = cols
                
                # Обновляем существующие комбобоксы
                for cb1, _ in self.common_fields:
                    cb1.clear()
                    cb1.addItems(cols)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")

    def load_file2(self):
        """Загрузка второго файла"""
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите второй файл", "", "Excel-файлы (*.xlsx *.xls)"
        )
        if path:
            try:
                self.file2 = path
                self.file2_label.setText(f"✅ {path}")
                cols = pd.read_excel(path).columns.tolist()
                self.columns_file2 = cols
                
                # Обновляем существующие комбобоксы
                for _, cb2 in self.common_fields:
                    cb2.clear()
                    cb2.addItems(cols)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")

    def merge(self):
        """Объединение файлов"""
        try:
            if not self.file1 or not self.file2:
                raise ValueError("Загрузите оба файла.")
            
            pairs = [
                (cb1.currentText(), cb2.currentText())
                for cb1, cb2 in self.common_fields
                if cb1.currentText() and cb2.currentText()
            ]
            
            if not pairs:
                raise ValueError("Добавьте хотя бы одну пару столбцов.")

            df1 = pd.read_excel(self.file1)
            df2 = pd.read_excel(self.file2)
            merged_df = merge_excel(df1, df2, pairs)

            # Сортировка по ФИО (если есть столбец ФИО_1)
            if 'ФИО_1' in merged_df.columns:
                merged_df = merged_df.sort_values(by='ФИО_1').reset_index(drop=True)

            # Подсчёт уникальных записей по первой таблице
            unique_count = merged_df['_idx1'].nunique() if '_idx1' in merged_df.columns else 0

            # Удаляем вспомогательные столбцы, если они есть
            cols_to_drop = ['join_key', '_idx1', '_idx2']
            cols_to_drop = [col for col in cols_to_drop if col in merged_df.columns]
            if cols_to_drop:
                merged_df.drop(columns=cols_to_drop, inplace=True)

            # Сохранение
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить объединенный файл", "merged_output.xlsx", "Excel-файлы (*.xlsx)"
            )
            
            if not save_path:
                return

            merged_df.to_excel(save_path, index=False)
            
            # Форматирование ширины столбцов
            try:
                wb = load_workbook(save_path)
                ws = wb.active
                for col in ws.columns:
                    max_len = max((len(str(cell.value)) for cell in col if cell.value), default=0)
                    ws.column_dimensions[col[0].column_letter].width = min(max_len + 5, 50)
                wb.save(save_path)
                wb.close()
            except Exception as e:
                print(f"⚠️ Не удалось отформатировать столбцы: {e}")

            QMessageBox.information(
                self,
                "✅ Успех",
                f"Файлы объединены!\n\n"
                f"📁 Сохранено в: {save_path}\n"
                f"📊 Уникальных записей: {unique_count}"
            )
        except Exception as e:
            err = traceback.format_exc()
            print(err)
            QMessageBox.critical(self, "❌ Ошибка", str(e))
