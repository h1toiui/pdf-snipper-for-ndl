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
    ProcessingOptions,
)
from pdf_processor import normalize_output_path, process_documents
from widgets import SELECTION_SINGLE_PAGE, SELECTION_TWO_PAGE, SelectionLabel


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
        """PDF追加、解除、並び替え用のUIグループを作る。"""
        self.btn_select = QPushButton("PDFファイルを追加")
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
        self.check_ocr = QCheckBox("OCR（処理に時間がかかります）")

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
            QLabel("ファイル名:"),
            self.filename_input,
            QLabel("著者:"),
            self.author_input,
        ):
            layout.addWidget(widget)

        return self._group_box("出力オプション", layout)

    def _build_execution_group(self):
        """実行ボタン、進捗バー、状態メッセージのUIグループを作る。"""
        self.btn_run = QPushButton("実行")
        self.btn_run.setFixedHeight(50)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #007AFF;
                color: white;
            }
            QPushButton:disabled {
                background-color: #b8b8b8;
                color: #f2f2f2;
            }
            """)
        self.btn_run.clicked.connect(self.process_pdf)

        self.progress = QProgressBar()
        self._reset_progress()
        self.status_log = QLabel("待機中")

        layout = QVBoxLayout()
        layout.addWidget(self.btn_run)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_log)
        return self._group_box("実行", layout)

    def select_files(self):
        """ファイルダイアログで選ばれたPDFを一覧へ追加する。"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "PDFを選択", "", "PDF Files (*.pdf)"
        )
        is_first_add = self.file_list.count() == 0
        for file_path in sorted(files):
            self._add_file(file_path)

        if files:
            self._autofill_output_metadata()
            self.refresh_preview(reset_page=is_first_add)

    def remove_selected_files(self):
        """一覧で選択中のPDFを処理対象から外す。"""
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self.refresh_preview(reset_page=False)

    def refresh_preview(self, reset_page=False):
        """複合PDFのグローバルページを切り抜き用プレビューへ表示する。"""
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
        """全ファイルのページオフセットと総ページ数を返す。"""
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

        self._set_processing_state(True)
        try:
            result = process_documents(options, self._update_file_progress)
            self._set_progress_value(result.page_count, result.page_count)
            message = f"保存完了:\n{result.output_path}"
            self.status_log.setText(f"完了: {result.file_size_mb:.2f} MB")
            QMessageBox.information(self, "完了", message)
        except Exception as e:
            self._reset_progress()
            self.status_log.setText("エラー")
            QMessageBox.critical(self, "エラー", f"処理中にエラーが発生しました:\n{e}")
        finally:
            self._set_processing_state(False)

    def _validate_inputs(self):
        """実行に必要なPDF、切り抜き範囲、プレビューの有無を確認する。"""
        if self.file_list.count() == 0:
            QMessageBox.warning(self, "エラー", "ファイルを選択してください")
            return False
        if not self.canvas.selected_rects():
            QMessageBox.warning(self, "エラー", "範囲を指定してください")
            return False
        if self.canvas.pixmap().isNull():
            QMessageBox.warning(self, "エラー", "プレビュー画像を読み込めませんでした")
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
        )

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
        """一覧に並んでいるPDFパスを表示順で返す。"""
        return [
            self.file_list.item(i).data(Qt.UserRole)
            for i in range(self.file_list.count())
        ]

    def _ocr_command(self):
        """環境変数、ローカルvenv、PATHの順にNDLOCR-Liteコマンドを探す。"""
        env_command = os.environ.get("NDLOCR_LITE_COMMAND")
        if env_command:
            return env_command

        app_dir = os.path.dirname(os.path.abspath(__file__))
        local_command = os.path.join(app_dir, ".venv-ndlocr", "bin", "ndlocr-lite")
        if os.path.exists(local_command):
            return local_command

        resolved = shutil.which("ndlocr-lite")
        return resolved or "ndlocr-lite"

    def _add_file(self, file_path):
        """PDFパスを表示名付きのリスト項目として追加する。"""
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
        """先頭PDFのメタデータからタイトルと著者を未編集欄へ自動入力する。"""
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
        if stage == "prepare":
            self._set_progress_value(0, total)
            self.status_log.setText(f"処理準備中: 0 / {total} ページ")
        elif stage == "render":
            self._set_progress_value(current, total)
            self.status_log.setText(f"ページ画像を生成中: {current} / {total} ページ")
        elif stage == "ocr":
            self._set_busy_progress()
            self.status_log.setText("OCR処理中: NDLOCR-Liteの完了を待っています")
        elif stage == "ocr_done":
            self._set_progress_value(current, total)
            self.status_log.setText(f"OCR完了: {current} / {total} ページ")
        elif stage == "embed":
            self._set_progress_value(current, total)
            self.status_log.setText("OCRテキストを埋め込み中")
        elif stage == "save":
            self._set_progress_value(current, total)
            self.status_log.setText("ファイル保存中")
        else:
            self._set_progress_value(current, total)
            self.status_log.setText(f"処理中: {current} / {total}")
        self.progress.repaint()
        self.status_log.repaint()
        QApplication.processEvents()

    def _set_processing_state(self, is_processing):
        """実行中かどうかに応じてボタンと初期メッセージを切り替える。"""
        self.btn_run.setEnabled(not is_processing)
        if is_processing:
            self._set_busy_progress()
            self.status_log.setText("処理を開始しています")

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
