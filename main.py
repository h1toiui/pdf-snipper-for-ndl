import sys
import os
import fitz  # PyMuPDF
from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFileDialog, QLabel, QRadioButton, 
                             QProgressBar, QMessageBox, QListWidget, QListWidgetItem, QAbstractItemView,
                             QLineEdit, QGroupBox, QButtonGroup)
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PySide6.QtCore import Qt, QRect, QPoint

class SelectionLabel(QLabel):
    """画像上でマウスドラッグして矩形を選択するクラス（2点指定）"""
    def __init__(self):
        super().__init__()
        self.setScaledContents(True)
        self.rect_p1 = QRect()
        self.rect_p2 = QRect()
        self.mode = 1  # 1: 1ページ目, 2: 2ページ目
        self.start_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            rect = QRect(self.start_pos, event.pos()).normalized()
            if self.mode == 1: self.rect_p1 = rect
            else: self.rect_p2 = rect
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if not self.rect_p1.isNull():
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.drawRect(self.rect_p1)
            painter.drawText(self.rect_p1.topLeft(), "Page 1")
        if not self.rect_p2.isNull():
            painter.setPen(QPen(QColor(0, 0, 255), 2))
            painter.drawRect(self.rect_p2)
            painter.drawText(self.rect_p2.topLeft(), "Page 2")

class PDFSnipper(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf-snipper for ndl")
        self.resize(1100, 850)
        
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        side_layout = QVBoxLayout()

        # --- 1. インポート（ドラッグで並び替え） ---
        file_group = QGroupBox("1. インポート（ドラッグで並び替え）")
        file_vbox = QVBoxLayout()
        self.btn_select = QPushButton("PDFファイルを追加")
        self.btn_select.clicked.connect(self.select_files)
        self.btn_remove = QPushButton("選択したファイルを解除")
        self.btn_remove.clicked.connect(self.remove_selected_files)
        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QAbstractItemView.InternalMove) # 並び替え有効
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        file_vbox.addWidget(self.btn_select)
        file_vbox.addWidget(self.btn_remove)
        file_vbox.addWidget(self.file_list)
        file_group.setLayout(file_vbox)

        # --- 2. 切り抜き範囲指定 ---
        crop_group = QGroupBox("2. 切り抜き範囲指定")
        crop_vbox = QVBoxLayout()
        self.mode_label = QLabel("現在のモード: 1ページ目（赤）")
        self.btn_toggle_mode = QPushButton("1P / 2P切替")
        self.btn_toggle_mode.clicked.connect(self.toggle_mode)
        crop_vbox.addWidget(self.mode_label)
        crop_vbox.addWidget(self.btn_toggle_mode)
        crop_group.setLayout(crop_vbox)

        # --- 3. 出力設定 ---
        out_group = QGroupBox("3. 出力オプション")
        out_vbox = QVBoxLayout()
        self.check_color = QRadioButton("カラー（元のまま）")
        self.check_bw = QRadioButton("グレースケール")
        self.check_color.setChecked(True)
        
        # 圧縮ラジオボタン
        self.comp_group = QButtonGroup()
        self.radio_none = QRadioButton("元のまま")
        self.radio_std = QRadioButton("標準圧縮（150dpi）")
        self.radio_high = QRadioButton("高圧縮（96dpi）")
        self.radio_std.setChecked(True)
        self.comp_group.addButton(self.radio_none)
        self.comp_group.addButton(self.radio_std)
        self.comp_group.addButton(self.radio_high)

        self.filename_input = QLineEdit("吾輩は猫である_combined")
        self.filename_input.setPlaceholderText("出力ファイル名を入力")

        out_vbox.addWidget(self.check_color)
        out_vbox.addWidget(self.check_bw)
        out_vbox.addWidget(QLabel("圧縮レベル:"))
        out_vbox.addWidget(self.radio_none)
        out_vbox.addWidget(self.radio_std)
        out_vbox.addWidget(self.radio_high)
        out_vbox.addWidget(QLabel("出力ファイル名:"))
        out_vbox.addWidget(self.filename_input)
        out_group.setLayout(out_vbox)

        # --- 4. 実行エリア ---
        exec_group = QGroupBox("4. 実行")
        exec_vbox = QVBoxLayout()
        self.btn_run = QPushButton("実行")
        self.btn_run.setFixedHeight(50)
        self.btn_run.setStyleSheet("background-color: #007AFF; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.process_pdf)
        self.progress = QProgressBar()
        self.status_log = QLabel("")  # 待機中
        exec_vbox.addWidget(self.btn_run)
        exec_vbox.addWidget(self.progress)
        exec_vbox.addWidget(self.status_log)
        exec_group.setLayout(exec_vbox)

        # レイアウト配置
        side_layout.addWidget(file_group)
        side_layout.addWidget(crop_group)
        side_layout.addWidget(out_group)
        side_layout.addWidget(exec_group)
        
        self.canvas = SelectionLabel()
        self.canvas.setStyleSheet("border: 2px solid #ccc; background-color: #eee;")

        main_layout.addLayout(side_layout, 1)
        main_layout.addWidget(self.canvas, 3)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "PDFを選択", "", "PDF Files (*.pdf)")
        if files:
            for f in sorted(files):
                item = QListWidgetItem(os.path.basename(f))
                item.setData(Qt.UserRole, f)
                self.file_list.addItem(item)
            self.refresh_preview()

    def remove_selected_files(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self.refresh_preview()

    def refresh_preview(self):
        if self.file_list.count() == 0: return
        first_file = self.file_list.item(0).data(Qt.UserRole)
        with fitz.open(first_file) as doc:
            page = doc[len(doc) // 2]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))  # 表示倍率
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            self.canvas.setPixmap(QPixmap.fromImage(img))

    def toggle_mode(self):
        self.canvas.mode = 2 if self.canvas.mode == 1 else 1
        txt = "2ページ目（青）" if self.canvas.mode == 2 else "1ページ目（赤）"
        self.mode_label.setText(f"現在のモード: {txt}")

    def process_pdf(self):
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "エラー", "ファイルを選択してください")
            return
        if self.canvas.rect_p1.isNull():
            QMessageBox.warning(self, "エラー", "範囲を指定してください")
            return

        save_dir = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if not save_dir: return

        # 圧縮設定の決定
        dpi = 300 if self.radio_none.isChecked() else (150 if self.radio_std.isChecked() else 96)
        zoom = dpi / 72
        
        filename = self.filename_input.text()
        if not filename.endswith(".pdf"): filename += ".pdf"
        save_path = os.path.join(save_dir, filename)

        new_doc = fitz.open()
        total_files = self.file_list.count()
        self.progress.setMaximum(total_files)

        try:
            for i in range(total_files):
                file_path = self.file_list.item(i).data(Qt.UserRole)
                with fitz.open(file_path) as doc:
                    for page in doc:
                        for q_rect in [self.canvas.rect_p1, self.canvas.rect_p2]:
                            if q_rect.isNull(): continue
                            
                            # 座標変換
                            scale_x = page.rect.width / self.canvas.pixmap().width()
                            scale_y = page.rect.height / self.canvas.pixmap().height()
                            pdf_rect = fitz.Rect(q_rect.left()*scale_x, q_rect.top()*scale_y, 
                                               q_rect.right()*scale_x, q_rect.bottom()*scale_y)
                            
                            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=pdf_rect,
                                                colorspace=fitz.csGRAY if self.check_bw.isChecked() else fitz.csRGB)
                            
                            img_page = new_doc.new_page(width=pdf_rect.width, height=pdf_rect.height)
                            img_page.insert_image(img_page.rect, pixmap=pix)

                self.progress.setValue(i + 1)
                self.status_log.setText(f"処理中: {i+1}/{total_files}")
                QApplication.processEvents()

            new_doc.save(save_path, garbage=3, deflate=True)
            size = os.path.getsize(save_path) / (1024*1024)
            self.status_log.setText(f"完了: {size:.2f} MB")
            QMessageBox.information(self, "完了", f"保存完了:\n{save_path}")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"処理中にエラーが発生しました:\n{e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDFSnipper()
    window.show()
    sys.exit(app.exec())
