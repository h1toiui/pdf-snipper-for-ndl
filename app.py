import os
import shutil

import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from models import (
    EPUB_LTR,
    EPUB_RTL,
    IMAGE_PROCESS_ENHANCE,
    IMAGE_PROCESS_NONE,
    OUTPUT_EPUB,
    OUTPUT_PDF,
    ProcessingOptions,
)
from pdf_processor import normalize_output_path, process_documents
from widgets import SelectionLabel


class PDFSnipper(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("pdf-snipper for ndl")
        self.resize(1100, 850)
        self._build_ui()

    def _build_ui(self):
        side_layout = QVBoxLayout()
        side_layout.addWidget(self._build_file_group())
        side_layout.addWidget(self._build_crop_group())
        side_layout.addWidget(self._build_output_group())
        side_layout.addWidget(self._build_execution_group())

        self.canvas = SelectionLabel()
        self.canvas.setStyleSheet("border: 2px solid #ccc; background-color: #eee;")

        main_layout = QHBoxLayout()
        main_layout.addLayout(side_layout, 1)
        main_layout.addWidget(self.canvas, 3)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def _build_file_group(self):
        self.btn_select = QPushButton("PDFファイルを追加")
        self.btn_select.clicked.connect(self.select_files)

        self.btn_remove = QPushButton("選択したファイルを解除")
        self.btn_remove.clicked.connect(self.remove_selected_files)

        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_select)
        layout.addWidget(self.btn_remove)
        layout.addWidget(self.file_list)
        return self._group_box("1. インポート（ドラッグで並び替え）", layout)

    def _build_crop_group(self):
        self.radio_scan_spread = QRadioButton("見開き")
        self.radio_scan_single = QRadioButton("単一ページ")
        self.radio_scan_spread.setChecked(True)
        self.scan_type_group = self._button_group(
            self.radio_scan_spread,
            self.radio_scan_single,
        )
        self.radio_scan_spread.toggled.connect(self.update_scan_type)

        self.mode_label = QLabel("現在のモード: 1ページ目（赤）")
        self.btn_toggle_mode = QPushButton("1P / 2P切替")
        self.btn_toggle_mode.clicked.connect(self.toggle_mode)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("スキャンタイプ:"))
        layout.addWidget(self.radio_scan_spread)
        layout.addWidget(self.radio_scan_single)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.btn_toggle_mode)
        return self._group_box("2. 切り抜き範囲指定", layout)

    def _build_output_group(self):
        self.check_color = QRadioButton("元のまま")
        self.check_bw = QRadioButton("グレースケール")
        self.check_enhance = QRadioButton("白黒二極化")
        self.check_enhance.setChecked(True)
        self.color_group = self._button_group(
            self.check_color,
            self.check_bw,
            self.check_enhance,
        )

        self.radio_none = QRadioButton("元のまま")
        self.radio_std = QRadioButton("標準圧縮（96dpi）")
        self.radio_high = QRadioButton("高圧縮（48dpi）")
        self.radio_std.setChecked(True)
        self.comp_group = self._button_group(self.radio_none, self.radio_std, self.radio_high)

        self.radio_pdf = QRadioButton("PDF")
        self.radio_epub_ltr = QRadioButton("EPUB（左綴じ）")
        self.radio_epub_rtl = QRadioButton("EPUB（右綴じ）")
        self.radio_epub_rtl.setChecked(True)
        self.format_group = self._button_group(
            self.radio_pdf,
            self.radio_epub_ltr,
            self.radio_epub_rtl,
        )
        self.radio_pdf.toggled.connect(self.update_ocr_option)
        self.radio_epub_ltr.toggled.connect(self.update_ocr_option)
        self.radio_epub_rtl.toggled.connect(self.update_ocr_option)

        self.check_ocr = QCheckBox("OCRテキストをEPUBに埋め込む")

        self.filename_input = QLineEdit("女ゲリラたち")
        self.filename_input.setPlaceholderText("出力ファイル名を入力")

        layout = QVBoxLayout()
        for widget in (
            QLabel("カラー:"),
            self.check_color,
            self.check_bw,
            self.check_enhance,
            QLabel("圧縮レベル:"),
            self.radio_none,
            self.radio_std,
            self.radio_high,
            QLabel("出力形式:"),
            self.radio_pdf,
            self.radio_epub_ltr,
            self.radio_epub_rtl,
            self.check_ocr,
            QLabel("出力ファイル名:"),
            self.filename_input,
        ):
            layout.addWidget(widget)

        self.update_ocr_option()
        return self._group_box("3. 出力オプション", layout)

    def _build_execution_group(self):
        self.btn_run = QPushButton("実行")
        self.btn_run.setFixedHeight(50)
        self.btn_run.setStyleSheet("background-color: #007AFF; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.process_pdf)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("0 / 0")
        self.status_log = QLabel("待機中")

        layout = QVBoxLayout()
        layout.addWidget(self.btn_run)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_log)
        return self._group_box("4. 実行", layout)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "PDFを選択", "", "PDF Files (*.pdf)")
        for file_path in sorted(files):
            self._add_file(file_path)

        if files:
            self.refresh_preview()

    def remove_selected_files(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self.refresh_preview()

    def refresh_preview(self):
        if self.file_list.count() == 0:
            self.canvas.clear()
            self.canvas.clear_selection()
            return

        first_file = self.file_list.item(0).data(Qt.UserRole)
        with fitz.open(first_file) as doc:
            page = doc[len(doc) // 2]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            self.canvas.setPixmap(QPixmap.fromImage(image.copy()))

    def toggle_mode(self):
        self.canvas.toggle_mode()
        label = "2ページ目（青）" if self.canvas.mode == 2 else "1ページ目（赤）"
        self.mode_label.setText(f"現在のモード: {label}")

    def update_scan_type(self):
        is_spread = self.radio_scan_spread.isChecked()
        self.canvas.set_spread_mode(is_spread)
        self.btn_toggle_mode.setEnabled(is_spread)
        if is_spread:
            self.mode_label.setText("現在のモード: 1ページ目（赤）")
        else:
            self.mode_label.setText("現在のモード: 単一ページ（赤）")

    def update_ocr_option(self):
        is_epub = self.radio_epub_ltr.isChecked() or self.radio_epub_rtl.isChecked()
        self.check_ocr.setEnabled(is_epub)
        if not is_epub:
            self.check_ocr.setChecked(False)

    def process_pdf(self):
        if not self._validate_inputs():
            return

        save_dir = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if not save_dir:
            return

        self._set_processing_state(True)
        try:
            options = self._build_processing_options(save_dir)
            result = process_documents(options, self._update_file_progress)
            self.progress.setValue(self.progress.maximum())
            message = f"保存完了:\n{result.output_path}"
            if result.ocr_embedded:
                message += "\n\nOCRテキストをEPUBに埋め込みました"
            self.status_log.setText(f"完了: {result.file_size_mb:.2f} MB")
            QMessageBox.information(self, "完了", message)
        except Exception as e:
            self.status_log.setText("エラー")
            QMessageBox.critical(self, "エラー", f"処理中にエラーが発生しました:\n{e}")
        finally:
            self._set_processing_state(False)

    def _validate_inputs(self):
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "エラー", "ファイルを選択してください")
            return False
        if not self.canvas.selected_rects():
            QMessageBox.warning(self, "エラー", "範囲を指定してください")
            return False
        if self.canvas.pixmap() is None:
            QMessageBox.warning(self, "エラー", "プレビュー画像を読み込めませんでした")
            return False
        return True

    def _build_processing_options(self, save_dir):
        output_format = OUTPUT_PDF if self.radio_pdf.isChecked() else OUTPUT_EPUB
        output_path, output_title = normalize_output_path(
            save_dir,
            self.filename_input.text(),
            output_format,
        )

        return ProcessingOptions(
            file_paths=self._file_paths(),
            output_path=output_path,
            output_title=output_title,
            crop_rects=self.canvas.selected_rects(),
            viewport_width=max(1, self.canvas.width()),
            viewport_height=max(1, self.canvas.height()),
            dpi=self._selected_dpi(),
            grayscale=self.check_bw.isChecked() or self.check_enhance.isChecked(),
            output_format=output_format,
            epub_direction=EPUB_RTL if self.radio_epub_rtl.isChecked() else EPUB_LTR,
            image_processing=self._selected_image_processing(),
            ocr_text_output=output_format == OUTPUT_EPUB and self.check_ocr.isChecked(),
            ocr_command=self._ocr_command(),
        )

    def _selected_image_processing(self):
        if self.check_enhance.isChecked():
            return IMAGE_PROCESS_ENHANCE
        return IMAGE_PROCESS_NONE

    def _selected_dpi(self):
        if self.radio_none.isChecked():
            return 300
        if self.radio_std.isChecked():
            return 96
        return 48

    def _file_paths(self):
        return [self.file_list.item(i).data(Qt.UserRole) for i in range(self.file_list.count())]

    def _ocr_command(self):
        env_command = os.environ.get("NDLOCR_LITE_COMMAND")
        if env_command:
            return env_command

        local_command = os.path.join(os.getcwd(), ".venv-ndlocr", "bin", "ndlocr-lite")
        if os.path.exists(local_command):
            return local_command

        resolved = shutil.which("ndlocr-lite")
        return resolved or "ndlocr-lite"

    def _add_file(self, file_path):
        item = QListWidgetItem(os.path.basename(file_path))
        item.setData(Qt.UserRole, file_path)
        self.file_list.addItem(item)

    def _update_file_progress(self, stage, current, total):
        if stage == "ocr":
            self.progress.setRange(0, max(1, total))
            self.progress.setValue(current)
            self.status_log.setText("OCR処理中" if current < total else "OCR完了")
            QApplication.processEvents()
            return

        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        self.status_log.setText(f"PDF処理中: {current} / {total}")
        QApplication.processEvents()

    def _set_processing_state(self, is_processing):
        self.btn_run.setEnabled(not is_processing)
        total_files = self.file_list.count()
        self.progress.setRange(0, max(1, total_files))
        self.progress.setFormat("%v / %m" if total_files else "0 / 0")
        if is_processing:
            self.progress.setValue(0)
            self.status_log.setText("PDF処理中")

    @staticmethod
    def _button_group(*buttons):
        group = QButtonGroup()
        for button in buttons:
            group.addButton(button)
        return group

    @staticmethod
    def _group_box(title, layout):
        group = QGroupBox(title)
        group.setLayout(layout)
        return group
