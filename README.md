# PDF Snipper For NDL

<img width="2340" height="1858" alt="Image" src="https://github.com/user-attachments/assets/2e8e23f4-3775-462d-8ffd-c0767d9ae534" />

国立国会図書館デジタルコレクションから分割ダウンロードしたPDFを、まとめて読みやすいPDFやEPUBにするためのデスクトップアプリです。

PDFを追加して並び替え、必要な範囲を切り抜き、電子書籍リーダー向けに圧縮して出力できます。

## できること

- 複数PDFの結合と並び替え
- 見開きモード / 2ページモードでの切り抜き
- カラー、グレースケール、白黒二極化
- PDF / EPUB出力
- EPUBの左綴じ / 右綴じ指定
- OCRテキストの埋め込み

## セットアップ

Python 3.12で動作確認しています。

```bash
cd pdf-snipper-for-ndl
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

OCRを使う場合は、別途NDLOCR-Liteも用意してください。

```bash
python3.12 -m venv .venv-ndlocr
.venv-ndlocr/bin/python -m pip install git+https://github.com/ndl-lab/ndlocr-lite.git
```

## 起動

```bash
source .venv/bin/activate
python main.py
```

## 使い方

1. `PDFファイルを追加` でPDFを追加します。
2. 必要ならリストをドラッグして順番を変えます。
3. `見開き` または `左右分割` と、切り抜き枠のアスペクト比を選びます。
4. 必要ならプレビュー下部の `前へ` `次へ` で確認するページを移動します。
5. 枠内部のドラッグで位置を調整し、枠上のハンドラーで大きさを調整します。
6. 出力形式、画質、ファイル名、著者を確認します。
7. OCRが必要なら `OCR` を有効にします。
8. `実行` を押して保存先を選びます。

## 注意

- 著作権および国立国会図書館など他サービスの利用規約を遵守してください。
- 著作物の複製（本アプリでの加工を含む）は私的利用においてのみ許可されています。
