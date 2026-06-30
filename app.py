import os
import shlex
import shutil
import sys

import fitz
from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
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
    QScrollArea,
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
    ProcessingCancelled,
    ProcessingOptions,
)
from pdf_processor import normalize_output_path, process_documents
from widgets import SELECTION_SINGLE_PAGE, SELECTION_TWO_PAGE, SelectionLabel

STATUS_IDLE = "待機中"
STATUS_STARTING = "処理を開始しています"
STATUS_ERROR = "エラー"
STATUS_COMPLETE = "完了: {file_size_mb:.2f} MB"
STATUS_PROGRESS_MESSAGES = {
    "prepare": "処理準備中: 0 / {total} ページ",
    "render": "ページ画像を生成中: {current} / {total} ページ",
    "ocr": "OCR処理中: NDLOCR-Liteの完了を待っています",
    "ocr_done": "OCR完了: {current} / {total} ページ",
    "embed": "OCRテキストを埋め込み中",
    "save": "ファイル保存中",
    "default": "処理中: {current} / {total}",
}


class ProcessingWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, options):
        super().__init__()
        self._options = options
        self._cancel_requested = False

    @Slot()
    def run(self):
        """PDF/EPUB生成をワーカースレッド上で実行する。"""
        try:
            result = process_documents(
                self._options,
                self.progress.emit,
                self.is_cancel_requested,
            )
        except ProcessingCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)

    def cancel(self):
        """UIスレッドから呼ばれる中止要求。"""
        self._cancel_requested = True

    def is_cancel_requested(self):
        return self._cancel_requested


class PDFSnipper(QMainWindow):
    def __init__(self):
        """メインウィンドウを初期化してUIを構築する。"""
        super().__init__()
        self.setWindowTitle("PDF Snipper For NDL")
        self.resize(1100, 850)
        self._title_was_edited = False
        self._author_was_edited = False
        self._preview_global_page_index = 0
        self._preview_total_page_count = 0
        self._cover_image_path = ""
        self._processing_thread = None
        self._processing_worker = None
        self._cancel_requested = False
        self._build_ui()

    def _build_ui(self):
        """左側の操作パネルと右側のプレビュー領域を組み立てる。"""
        side_layout = QVBoxLayout()
        side_layout.addWidget(self._build_file_group())
        side_layout.addWidget(self._build_crop_group())
        side_layout.addWidget(self._build_output_group())
        side_layout.addWidget(self._build_execution_group())

        side_widget = QWidget()
        side_widget.setLayout(side_layout)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setWidget(side_widget)
        side_scroll.setMinimumWidth(320)

        self.canvas = SelectionLabel()
        self.canvas.setStyleSheet("border: 2px solid #ccc; background-color: #eee;")

        self.btn_preview_previous = self._build_preview_button("前へ", -1)
        self.preview_page_label = QLabel("0 / 0")
        self.preview_page_label.setAlignment(Qt.AlignCenter)
        self.btn_preview_next = self._build_preview_button("次へ", 1)

        page_nav_buttons = QVBoxLayout()
        page_nav_buttons.setSpacing(8)
        page_nav_buttons.addWidget(self.btn_preview_previous, alignment=Qt.AlignHCenter)
        page_nav_buttons.addWidget(self.preview_page_label, alignment=Qt.AlignHCenter)
        page_nav_buttons.addWidget(self.btn_preview_next, alignment=Qt.AlignHCenter)

        preview_controls = QHBoxLayout()
        preview_controls.setSpacing(10)
        preview_controls.addStretch()
        preview_controls.addLayout(page_nav_buttons)
        preview_controls.addStretch()

        preview_layout = QVBoxLayout()
        preview_layout.addWidget(self.canvas, 1)
        preview_layout.addLayout(preview_controls)
        preview_widget = QWidget()
        preview_widget.setLayout(preview_layout)

        main_layout = QHBoxLayout()
        main_layout.addWidget(side_scroll, 1)
        main_layout.addWidget(preview_widget, 3)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        self._update_preview_controls()

    def _build_file_group(self):
        """PDF / 画像の追加、解除、並び替え用のUIグループを作る。"""
        self.btn_select = QPushButton("PDF / 画像を追加")
        self.btn_select.clicked.connect(self.select_files)

        self.btn_remove = QPushButton("選択したファイルを解除")
        self.btn_remove.clicked.connect(self.remove_selected_files)

        self.file_list = QListWidget()
        self.file_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.model().rowsMoved.connect(
            lambda *args: self._on_file_list_moved()
        )

        layout = QVBoxLayout()
        layout.addWidget(self.btn_select)
        layout.addWidget(self.btn_remove)
        layout.addWidget(self.file_list)
        return self._group_box("インポート（ドラッグで並び替え）", layout)

    def _build_preview_button(self, label, offset):
        """プレビューページ移動ボタンを作る。"""
        button = QPushButton(label)
        button.setAutoRepeat(True)
        button.setAutoRepeatDelay(300)
        button.setAutoRepeatInterval(120)
        button.clicked.connect(lambda: self.change_preview_page(offset))
        return button

    def _build_crop_group(self):
        """スキャン種別と切り抜き範囲指定用のUIグループを作る。"""
        self.radio_mode_single_page = QRadioButton("シングルページ")
        self.radio_mode_two_page = QRadioButton("2ページ")
        self.radio_mode_single_page.setChecked(True)
        self.selection_mode_group = self._button_group(
            self.radio_mode_single_page,
            self.radio_mode_two_page,
        )
        self.radio_mode_single_page.toggled.connect(self.update_selection_mode)
        self.radio_mode_two_page.toggled.connect(self.update_selection_mode)

        self.aspect_ratio_combo = QComboBox()
        self.aspect_ratio_combo.addItem("自由選択", "free")
        self.aspect_ratio_combo.addItem("元のアスペクト比", "source")
        self.aspect_ratio_combo.addItem("9:16（スマートフォン）", 9 / 16)
        self.aspect_ratio_combo.addItem("1:1.414（A判・B判）", 1 / 1.414)
        self.aspect_ratio_combo.currentIndexChanged.connect(self.update_aspect_ratio)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("切り抜きモード:"))
        layout.addWidget(self.radio_mode_single_page)
        layout.addWidget(self.radio_mode_two_page)
        layout.addWidget(QLabel("アスペクト比:"))
        layout.addWidget(self.aspect_ratio_combo)
        return self._group_box("切り抜き範囲指定", layout)

    def _build_output_group(self):
        """色、圧縮、形式、OCR、書誌情報の出力オプションを作る。"""
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
        self.comp_group = self._button_group(
            self.radio_none, self.radio_std, self.radio_high
        )

        self.radio_pdf = QRadioButton("PDF")
        self.radio_epub_ltr = QRadioButton("EPUB（左綴じ）")
        self.radio_epub_rtl = QRadioButton("EPUB（右綴じ）")
        self.radio_epub_rtl.setChecked(True)
        self.format_group = self._button_group(
            self.radio_pdf,
            self.radio_epub_ltr,
            self.radio_epub_rtl,
        )
        self.radio_pdf.toggled.connect(self._update_cover_image_controls)
        self.radio_epub_ltr.toggled.connect(self._update_cover_image_controls)
        self.radio_epub_rtl.toggled.connect(self._update_cover_image_controls)
        self.check_ocr = QCheckBox("OCR（処理に時間がかかります）")

        self.cover_image_title_label = QLabel("表紙:")
        self.btn_select_cover = QPushButton("表紙画像を選択")
        self.btn_select_cover.clicked.connect(self.select_cover_image)
        self.cover_image_label = QLabel()
        self.cover_image_label.setWordWrap(True)

        self.filename_input = QLineEdit()
        self.filename_input.textEdited.connect(
            lambda: setattr(self, "_title_was_edited", True)
        )

        self.author_input = QLineEdit()
        self.author_input.textEdited.connect(
            lambda: setattr(self, "_author_was_edited", True)
        )

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
            self.cover_image_title_label,
            self.btn_select_cover,
            self.cover_image_label,
            QLabel("ファイル名:"),
            self.filename_input,
            QLabel("著者:"),
            self.author_input,
        ):
            layout.addWidget(widget)

        self._update_cover_image_controls()
        return self._group_box("出力オプション", layout)

    def _build_execution_group(self):
        """実行ボタン、進捗バー、状態メッセージのUIグループを作る。"""
        self.btn_run = QPushButton("実行")
        self.btn_run.setFixedHeight(50)
        self.btn_run.clicked.connect(self._on_run_button_clicked)
        self._set_run_button_style(is_processing=False)

        self.progress = QProgressBar()
        self._reset_progress()
        self.status_log = QLabel(STATUS_IDLE)

        layout = QVBoxLayout()
        layout.addWidget(self.btn_run)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_log)
        return self._group_box("実行", layout)

    def select_files(self):
        """ファイルダイアログで選ばれたPDF / 画像を一覧へ追加する。"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "PDF / 画像を選択",
            "",
            "Documents and Images (*.pdf *.png *.jpg *.jpeg);;PDF Files (*.pdf);;Image Files (*.png *.jpg *.jpeg)",
        )
        is_first_add = self.file_list.count() == 0
        for file_path in sorted(files):
            self._add_file(file_path)

        if files:
            self._autofill_output_metadata()
            self.refresh_preview(reset_page=is_first_add)

    def select_cover_image(self):
        """EPUB表紙として埋め込む画像を選択する。キャンセル時は選択を解除する。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "表紙画像を選択",
            "",
            "Image Files (*.png *.jpg *.jpeg)",
        )
        self._cover_image_path = file_path or ""
        self._update_cover_image_controls()

    def remove_selected_files(self):
        """一覧で選択中のファイルを処理対象から外す。"""
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self.refresh_preview(reset_page=False)

    def refresh_preview(self, reset_page=False):
        """複合入力のグローバルページを切り抜き用プレビューへ表示する。"""
        if self.file_list.count() == 0:
            self.canvas.clear()
            self.canvas.clear_selection()
            self._preview_global_page_index = 0
            self._preview_total_page_count = 0
            self._update_preview_controls()
            return

        page_offsets, total_pages = self._collect_file_page_offsets()
        self._preview_total_page_count = total_pages
        if reset_page:
            self._preview_global_page_index = total_pages // 2
            self.canvas.clear_selection()
        self._preview_global_page_index = min(
            max(0, self._preview_global_page_index),
            max(0, total_pages - 1),
        )

        file_index, local_page_index = self._resolve_global_page(
            page_offsets, self._preview_global_page_index
        )
        file_path = self.file_list.item(file_index).data(Qt.UserRole)
        if not self._load_preview_page(file_path, local_page_index):
            self.canvas.clear()

        self._update_preview_controls()

    def _collect_file_page_offsets(self):
        """全入力のページオフセットと総ページ数を返す。"""
        offsets = [0]
        total_pages = 0
        for i in range(self.file_list.count()):
            file_path = self.file_list.item(i).data(Qt.UserRole)
            try:
                with fitz.open(file_path) as doc:
                    total_pages += len(doc)
            except Exception:
                pass
            offsets.append(total_pages)
        return offsets, total_pages

    def _resolve_global_page(self, page_offsets, global_page_index):
        """グローバルインデックスからファイルインデックスとローカルページインデックスを返す。"""
        for i in range(len(page_offsets) - 1):
            if page_offsets[i] <= global_page_index < page_offsets[i + 1]:
                return i, global_page_index - page_offsets[i]
        return max(0, len(page_offsets) - 2), 0

    def _load_preview_page(self, file_path, local_page_index):
        """指定ファイルのローカルページを読み込み、キャンバスに表示する。"""
        try:
            with fitz.open(file_path) as doc:
                first_page = doc[0]
                self.canvas.set_source_aspect_ratio(
                    first_page.rect.width / max(1, first_page.rect.height)
                )
                if self.aspect_ratio_combo.currentData() == "source":
                    self.canvas.set_aspect_ratio(self.canvas.source_aspect_ratio)

                page = doc[local_page_index]
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csRGB
                )
                image = QImage(
                    pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888
                )
                self.canvas.setPixmap(QPixmap.fromImage(image.copy()))
            return True
        except Exception:
            return False

    def change_preview_page(self, offset):
        """複合PDFのグローバルページを前後へ移動する。"""
        if self._preview_total_page_count == 0:
            return
        target = min(
            max(0, self._preview_global_page_index + offset),
            self._preview_total_page_count - 1,
        )
        if target == self._preview_global_page_index:
            return
        self._preview_global_page_index = target
        self.refresh_preview()

    def update_selection_mode(self, checked):
        """1P・2P設定を選択ウィジェットへ反映する。"""
        if not checked:
            return
        mode = (
            SELECTION_SINGLE_PAGE
            if self.radio_mode_single_page.isChecked()
            else SELECTION_TWO_PAGE
        )
        self.canvas.set_selection_mode(mode)

    def update_aspect_ratio(self, index=None):
        """選択中のアスペクト比を選択ウィジェットへ反映する。"""
        value = self.aspect_ratio_combo.currentData()
        if value == "free":
            ratio = None
        elif value == "source":
            ratio = self.canvas.source_aspect_ratio
        else:
            ratio = float(value)
        self.canvas.set_aspect_ratio(ratio)

    def _update_preview_controls(self):
        """ページ番号と前後ページボタンの有効状態を更新する。"""
        has_pages = self._preview_total_page_count > 0
        current = self._preview_global_page_index + 1 if has_pages else 0
        self.preview_page_label.setText(f"{current} / {self._preview_total_page_count}")
        self.btn_preview_previous.setEnabled(
            has_pages and self._preview_global_page_index > 0
        )
        self.btn_preview_next.setEnabled(
            has_pages
            and self._preview_global_page_index < self._preview_total_page_count - 1
        )

    def process_pdf(self):
        """入力検証後に保存先を選び、PDF/EPUB生成処理を実行する。"""
        if self._processing_thread is not None:
            return
        if not self._validate_inputs():
            return

        save_dir = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if not save_dir:
            return

        options = self._build_processing_options(save_dir)
        output_path = options.output_path
        output_title = options.output_title
        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self,
                "上書きの確認",
                f"{output_title} はすでに存在しています。\n上書きしますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._cancel_requested = False
        self._set_processing_state(True)
        self._start_processing_worker(options)

    def _on_run_button_clicked(self):
        """状態に応じて処理開始または中止要求を行う。"""
        if self._processing_thread is None:
            self.process_pdf()
        else:
            self.cancel_processing()

    def cancel_processing(self):
        """実行中の変換処理へ中止を要求する。"""
        if self._processing_worker is None:
            return
        self._cancel_requested = True
        self._processing_worker.cancel()
        self.btn_run.setEnabled(False)

    def _start_processing_worker(self, options):
        """変換処理をUIスレッドから切り離して開始する。"""
        self._processing_thread = QThread(self)
        self._processing_worker = ProcessingWorker(options)
        self._processing_worker.moveToThread(self._processing_thread)

        self._processing_thread.started.connect(self._processing_worker.run)
        self._processing_worker.progress.connect(self._update_file_progress)
        self._processing_worker.finished.connect(self._on_processing_finished)
        self._processing_worker.failed.connect(self._on_processing_failed)
        self._processing_worker.cancelled.connect(self._on_processing_cancelled)

        for signal in (
            self._processing_worker.finished,
            self._processing_worker.failed,
            self._processing_worker.cancelled,
        ):
            signal.connect(self._processing_thread.quit)
            signal.connect(self._processing_worker.deleteLater)

        self._processing_thread.finished.connect(self._processing_thread.deleteLater)
        self._processing_thread.finished.connect(self._clear_processing_worker)
        self._processing_thread.start()

    @Slot(object)
    def _on_processing_finished(self, result):
        """処理完了時のUI更新を行う。"""
        self._set_progress_value(result.page_count, result.page_count)
        message = f"保存完了:\n{result.output_path}"
        self._set_status(STATUS_COMPLETE, file_size_mb=result.file_size_mb)
        QMessageBox.information(self, "完了", message)
        self._set_processing_state(False)

    @Slot(str)
    def _on_processing_failed(self, message):
        """処理失敗時のUI更新を行う。"""
        self._reset_progress()
        self._set_status(STATUS_ERROR)
        QMessageBox.critical(
            self, "エラー", f"処理中にエラーが発生しました:\n{message}"
        )
        self._set_processing_state(False)

    @Slot()
    def _on_processing_cancelled(self):
        """中止完了時のUI更新を行う。ダイアログは表示しない。"""
        self._reset_progress()
        self._set_status(STATUS_IDLE)
        self._set_processing_state(False)

    @Slot()
    def _clear_processing_worker(self):
        """完了後にワーカー参照を破棄する。"""
        self._processing_thread = None
        self._processing_worker = None

    def _validate_inputs(self):
        """実行に必要な入力、切り抜き範囲、プレビューの有無を確認する。"""
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "エラー", "ファイルを選択してください")
            return False
        if not self.canvas.selected_rects():
            QMessageBox.warning(self, "エラー", "範囲を指定してください")
            return False
        if self.canvas.pixmap().isNull():
            QMessageBox.warning(self, "エラー", "プレビュー画像を読み込めませんでした")
            return False
        if self.check_ocr.isChecked() and not self._ocr_command():
            message_box = QMessageBox(self)
            message_box.setIcon(QMessageBox.Critical)
            message_box.setWindowTitle("NDLOCR-Liteが見つかりません")
            message_box.setText("NDLOCR-Liteが見つからないため、OCRを実行できません。")
            message_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Help)
            if message_box.exec() == QMessageBox.Help:
                QDesktopServices.openUrl(
                    QUrl(
                        "https://github.com/h1toiui/pdf-snipper-for-ndl#OCRのセットアップ"
                    )
                )
            return False
        return True

    def _build_processing_options(self, save_dir):
        """現在のUI状態から処理本体へ渡すオプションを作る。"""
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
            output_author=self.author_input.text().strip(),
            crop_rects=self.canvas.selected_rects(),
            viewport_width=self.canvas.image_width(),
            viewport_height=self.canvas.image_height(),
            dpi=self._selected_dpi(),
            grayscale=self.check_bw.isChecked() or self.check_enhance.isChecked(),
            output_format=output_format,
            epub_direction=EPUB_RTL if self.radio_epub_rtl.isChecked() else EPUB_LTR,
            image_processing=self._selected_image_processing(),
            ocr_text_output=self.check_ocr.isChecked(),
            ocr_command=self._ocr_command(),
            cover_image_path=(
                self._cover_image_path if output_format == OUTPUT_EPUB else ""
            ),
        )

    def _update_cover_image_controls(self, *args):
        """EPUB選択中だけ表紙画像UIを表示し、選択済みパスを表示する。"""
        is_epub = not self.radio_pdf.isChecked()
        self.cover_image_title_label.setVisible(is_epub)
        self.btn_select_cover.setVisible(is_epub)
        has_cover = bool(self._cover_image_path)
        self.cover_image_label.setVisible(is_epub and has_cover)
        if has_cover:
            self.cover_image_label.setText(f"✔︎ {self._cover_image_path}")

    def _selected_image_processing(self):
        """UIで選択された画像処理モードを返す。"""
        if self.check_enhance.isChecked():
            return IMAGE_PROCESS_ENHANCE
        return IMAGE_PROCESS_NONE

    def _selected_dpi(self):
        """UIで選択された圧縮レベルに対応するDPIを返す。"""
        if self.radio_none.isChecked():
            return 300
        if self.radio_std.isChecked():
            return 96
        return 48

    def _file_paths(self):
        """一覧に並んでいるファイルパスを表示順で返す。"""
        return [
            self.file_list.item(i).data(Qt.UserRole)
            for i in range(self.file_list.count())
        ]

    def _ocr_command(self):
        """環境変数、アプリ横のOCR環境、PATHの順にNDLOCR-Liteコマンドを探す。"""
        env_command = os.environ.get("NDLOCR_LITE_COMMAND")
        if env_command and self._is_available_command(env_command):
            return env_command

        for local_command in self._local_ocr_command_candidates():
            if os.path.exists(local_command):
                return local_command

        resolved = shutil.which("ndlocr-lite")
        if resolved:
            return resolved
        resolved = shutil.which("ndlocr-lite.exe")
        return resolved or ""

    def _local_ocr_command_candidates(self):
        """macOS/Linux/Windowsで使うアプリ横のOCRコマンド候補を返す。"""
        candidates = []
        for app_dir in self._application_dirs():
            candidates.extend(
                [
                    os.path.join(app_dir, ".venv-ndlocr", "bin", "ndlocr-lite"),
                    os.path.join(app_dir, ".venv-ndlocr", "Scripts", "ndlocr-lite.exe"),
                    os.path.join(app_dir, ".venv-ndlocr", "Scripts", "ndlocr-lite"),
                    os.path.join(app_dir, "ocr-runtime", "bin", "ndlocr-lite"),
                    os.path.join(app_dir, "ocr-runtime", "Scripts", "ndlocr-lite.exe"),
                    os.path.join(app_dir, "ocr-runtime", "Scripts", "ndlocr-lite"),
                ]
            )
        return candidates

    @staticmethod
    def _application_dir():
        """代表のアプリ配置ディレクトリを返す。"""
        return PDFSnipper._application_dirs()[0]

    @staticmethod
    def _application_dirs():
        """OCR環境を探す配置ディレクトリ候補を返す。"""
        if not getattr(sys, "frozen", False):
            return [os.path.dirname(os.path.abspath(__file__))]

        executable_dir = os.path.dirname(sys.executable)
        dirs = [executable_dir]

        if sys.platform == "darwin":
            contents_dir = os.path.dirname(executable_dir)
            bundle_dir = os.path.dirname(contents_dir)
            bundle_parent_dir = os.path.dirname(bundle_dir)
            dirs.extend([bundle_dir, bundle_parent_dir])

        unique_dirs = []
        for directory in dirs:
            if directory and directory not in unique_dirs:
                unique_dirs.append(directory)
        return unique_dirs

    @staticmethod
    def _is_available_command(command):
        """環境変数に指定されたコマンド文字列の実行ファイル部分を確認する。"""
        try:
            args = shlex.split(command, posix=os.name != "nt")
        except ValueError:
            return False
        if not args:
            return False

        executable = args[0]
        has_path_separator = os.sep in executable or (
            os.altsep is not None and os.altsep in executable
        )
        if has_path_separator:
            return os.path.exists(executable)
        return shutil.which(executable) is not None

    def _add_file(self, file_path):
        """ファイルパスを表示名付きのリスト項目として追加する。"""
        count = self.file_list.count() + 1
        display_text = f"{count}. {os.path.basename(file_path)}"
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, file_path)
        self.file_list.addItem(item)

    def _on_file_list_moved(self):
        self._renumber_file_list()
        self.refresh_preview(reset_page=False)

    def _renumber_file_list(self):
        """ファイルリストの項目番号を更新する。"""
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            file_path = item.data(Qt.UserRole)
            display_text = f"{i + 1}. {os.path.basename(file_path)}"
            item.setText(display_text)

    def _autofill_output_metadata(self):
        """先頭ファイルのメタデータからタイトルと著者を未編集欄へ自動入力する。"""
        if self.file_list.count() == 0:
            return

        file_path = self.file_list.item(0).data(Qt.UserRole)
        try:
            with fitz.open(file_path) as doc:
                metadata = doc.metadata or {}
        except Exception:
            return

        title = self._metadata_text(metadata, "title")
        author = self._metadata_text(metadata, "author")
        if not self._title_was_edited:
            self.filename_input.setText(title)
        if not self._author_was_edited:
            self.author_input.setText(author)

    @staticmethod
    def _metadata_text(metadata, key):
        """PyMuPDFのメタデータ辞書から空でない文字列を取り出す。"""
        value = metadata.get(key, "")
        if not isinstance(value, str):
            return ""
        return value.strip()

    def _update_file_progress(self, stage, current, total):
        """処理本体から通知された段階に応じて進捗表示を更新する。"""
        if self._cancel_requested:
            return
        status_template = STATUS_PROGRESS_MESSAGES.get(
            stage, STATUS_PROGRESS_MESSAGES["default"]
        )
        if stage == "prepare":
            self._set_progress_value(0, total)
        elif stage == "render":
            self._set_progress_value(current, total)
        elif stage == "ocr":
            self._set_busy_progress()
        elif stage == "ocr_done":
            self._set_progress_value(current, total)
        elif stage == "embed":
            self._set_progress_value(current, total)
        elif stage == "save":
            self._set_progress_value(current, total)
        else:
            self._set_progress_value(current, total)
        self._set_status(status_template, current=current, total=total)
        self.progress.repaint()
        self.status_log.repaint()

    def _set_processing_state(self, is_processing):
        """実行中かどうかに応じてボタンと初期メッセージを切り替える。"""
        self.btn_run.setEnabled(True)
        self.btn_run.setText("実行中止" if is_processing else "実行")
        self._set_run_button_style(is_processing)
        if is_processing:
            self._set_busy_progress()
            self._set_status(STATUS_STARTING)

    def _set_status(self, template, **values):
        """ステータス表示を一元的に更新する。"""
        self.status_log.setText(template.format(**values))

    def _set_run_button_style(self, is_processing):
        """実行ボタンの通常時/処理中の見た目を切り替える。"""
        background_color = "#a9a9a9" if is_processing else "#007AFF"
        disabled_color = "#a9a9a9" if is_processing else "#b8b8b8"
        self.btn_run.setStyleSheet(f"""
            QPushButton {{
                background-color: {background_color};
                color: white;
            }}
            QPushButton:disabled {{
                background-color: {disabled_color};
                color: #f2f2f2;
            }}
            """)

    def _reset_progress(self):
        """プログレスバーを待機時の空表示へ戻す。"""
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("0 / 0")

    def _set_busy_progress(self):
        """総量が分からない処理中であることをプログレスバーに表示する。"""
        self.progress.setRange(0, 0)
        self.progress.setFormat("")

    def _set_progress_value(self, current, total):
        """既知の総量に対する現在値をプログレスバーへ反映する。"""
        total = max(0, total)
        current = min(max(0, current), total)
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{current} / {total}" if total else "0 / 0")

    @staticmethod
    def _button_group(*buttons):
        """複数のラジオボタンを排他的なボタングループへまとめる。"""
        group = QButtonGroup()
        for button in buttons:
            group.addButton(button)
        return group

    @staticmethod
    def _group_box(title, layout):
        """指定タイトルとレイアウトを持つQGroupBoxを作る。"""
        group = QGroupBox(title)
        group.setLayout(layout)
        return group
