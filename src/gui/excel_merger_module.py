"""
"""


class ExcelMerger():
    def __init__(self, root):
        self.root = root
        self.root.title("Excel Merger")
        self.file1 = ""
        self.file2 = ""
        self.columns_file1 = []
        self.columns_file2 = []
        self.common_fields = []

        tk.Button(root, text="Загрузить первый файл", command=self.load_file1).pack(pady=10)
        self.file1_label = tk.Label(); self.file1_label.pack(pady=5)
        tk.Button(root, text="Загрузить второй файл", command=self.load_file2).pack(pady=10)
        self.file2_label = tk.Label(); self.file2_label.pack(pady=5)
        self.pair_frame = tk.Frame(root); self.pair_frame.pack(pady=10)
        tk.Button(root, text="Добавить пару столбцов для объединения", command=self.add_column_pair).pack(pady=5)
        tk.Button(root, text="Объединить файлы", command=self.merge).pack(pady=20)

    def add_column_pair(self):
        frame = tk.Frame(self.pair_frame); frame.pack(pady=5)
        cb1 = ttk.Combobox(frame, state="readonly", values=self.columns_file1); cb1.pack(side=tk.LEFT)
        cb2 = ttk.Combobox(frame, state="readonly", values=self.columns_file2); cb2.pack(side=tk.LEFT)
        tk.Button(frame, text="Удалить", command=lambda: self.remove_pair(frame, cb1, cb2)).pack(side=tk.LEFT)
        self.common_fields.append((cb1, cb2))

    def remove_pair(self, frame, cb1, cb2):
        val1, val2 = cb1.get(), cb2.get(); frame.destroy()
        self.common_fields = [(c1, c2) for c1, c2 in self.common_fields if (c1.get(), c2.get()) != (val1, val2)]

    def load_file1(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx;*.xls")])
        if path:
            self.file1 = path; self.file1_label.config(text=path)
            cols = pd.read_excel(path).columns.tolist()
            self.columns_file1 = cols
            for cb1, _ in self.common_fields: cb1['values'] = cols

    def load_file2(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx;*.xls")])
        if path:
            self.file2 = path; self.file2_label.config(text=path)
            cols = pd.read_excel(path).columns.tolist()
            self.columns_file2 = cols
            for _, cb2 in self.common_fields: cb2['values'] = cols

    def merge(self):
        try:
            if not self.file1 or not self.file2:
                raise ValueError("Загрузите оба файла.")
            pairs = [(cb1.get(), cb2.get()) for cb1, cb2 in self.common_fields if cb1.get() and cb2.get()]
            if not pairs:
                raise ValueError("Добавьте хотя бы одну пару столбцов.")

            df1 = pd.read_excel(self.file1)
            df2 = pd.read_excel(self.file2)
            merged_df = merge_excel(df1, df2, pairs)

            # Сортировка по ФИО (если есть столбец ФИО_1)
            if 'ФИО_1' in merged_df.columns:
                merged_df = merged_df.sort_values(by='ФИО_1').reset_index(drop=True)

            # Подсчёт уникальных записей по первой таблице
            unique_count = merged_df['_idx1'].nunique()

            # Удаляем вспомогательные столбцы
            merged_df.drop(columns=['join_key', '_idx1', '_idx2'], inplace=True)

            # Сохранение и форматирование
            out = "merged_output.xlsx"
            merged_df.to_excel(out, index=False)
            wb = load_workbook(out); ws = wb.active
            for col in ws.columns:
                max_len = max((len(str(cell.value)) for cell in col if cell.value), default=0)
                ws.column_dimensions[col[0].column_letter].width = max_len + 5
            wb.save(out); wb.close()

            messagebox.showinfo(
                "Успех",
                f"Файлы объединены в '{out}'.\n"
                f"Уникальных записей: {unique_count}"
            )
        except Exception as e:
            err = traceback.format_exc()
            print(err)
            messagebox.showerror("Ошибка", str(e))
