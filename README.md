# PDF Snipper For NDL

国立国会図書館（NDL） デジタルコレクションからは、最大100コマまでしかダウンロードできません。  
この分割されたPDFを、GUIを使って**結合・並び替え・切り抜き・圧縮**し、電子書籍アプリ / 端末で閲覧できるようにします。

## 機能

- PDF結合 & 並び替え
- 見開き / 単一ページの切り抜き範囲指定
- カラー / グレースケール / 白黒二極化
- 圧縮レベル選択
- PDF / EPUB出力
- EPUBのページ送り方向指定
- NDLOCR-LiteによるOCRテキスト埋め込み
  - PDF: 透明テキストレイヤーとして埋め込み
  - EPUB: 画像上の透明な位置付きテキストレイヤーとして埋め込み

## セットアップ

### 環境

- Python 3.12で動作確認済み
- macOSで動作確認済み
- OCRを使う場合は、通常のアプリ用仮想環境とは別にNDLOCR-Lite用仮想環境を作成します

### 1. アプリ本体のセットアップ

```bash
# プロジェクトフォルダへ移動
cd pdf-snipper-for-ndl

# 仮想環境の作成
python3 -m venv .venv

# 仮想環境の有効化
source .venv/bin/activate

# 必要なライブラリのインストール
pip install -r requirements.txt
```

### 2. NDLOCR-Liteのセットアップ（OCRを使う場合）

NDLOCR-Liteは依存ライブラリの都合でPython 3.12の利用を推奨します。  
Python 3.12がない場合は、macOSならHomebrewなどでインストールしてください。

```bash
# Python 3.12の確認
python3.12 --version

# NDLOCR-Lite専用の仮想環境を作成
python3.12 -m venv .venv-ndlocr

# NDLOCR-Liteをインストール
.venv-ndlocr/bin/python -m pip install git+https://github.com/ndl-lab/ndlocr-lite.git

# 動作確認
.venv-ndlocr/bin/ndlocr-lite --help
```

アプリは次の順でNDLOCR-Liteコマンドを探します。

1. 環境変数 `NDLOCR_LITE_COMMAND`
2. プロジェクト直下の `.venv-ndlocr/bin/ndlocr-lite`
3. `PATH` 上の `ndlocr-lite`

別の場所にインストールしたNDLOCR-Liteを使う場合は、次のように指定できます。

```bash
export NDLOCR_LITE_COMMAND="/path/to/ndlocr-lite"
```

## 起動

```bash
source .venv/bin/activate
python main.py
```

## 使い方

1. `PDFファイルを追加` でNDLからダウンロードしたPDFを追加します。
2. 必要に応じてリストをドラッグして並び替えます。
3. `スキャンタイプ` を `見開き` または `単一ページ` から選びます。
4. プレビュー画像上で切り抜き範囲をドラッグ指定します。
   - 見開き: `1P / 2P切替` で1ページ目・2ページ目の範囲を指定します。
   - 単一ページ: 1つの範囲だけを指定します。
5. カラー、圧縮レベル、出力形式、ファイル名を設定します。
6. OCRを埋め込む場合は `OCRテキストを埋め込む` を有効にします。
7. `実行` を押し、保存先フォルダを選択します。

## OCRについて

OCRを有効にすると、切り抜き後のページ画像をNDLOCR-Liteで解析し、PDFまたはEPUBへテキストを埋め込みます。

- PDF出力では、画像ページの上に透明テキストを重ねます。
- EPUB出力では、各ページのXHTMLに位置付きの透明テキストを埋め込みます。
- NDLOCR-Lite JSONの `isVertical` は使わず、`boundingBox` の幅と高さから縦横を判定します。
- OCR本文は、同じJSON `contents` ブロック内の改行を詰め、ブロック間だけ段落区切りとして扱います。

## 注意点

- OCRはCPUで実行されるため、ページ数が多いPDFでは時間がかかります。
- OCR精度は元画像の品質、文字の向き、レイアウトに依存します。
- Python 3.14ではNDLOCR-Liteの依存である `onnxruntime` が入らない場合があります。OCR用にはPython 3.12を使ってください。
