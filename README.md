# PDF Snipper For NDL

<img width="2340" height="1858" alt="Image" src="https://github.com/user-attachments/assets/2e8e23f4-3775-462d-8ffd-c0767d9ae534" />

国立国会図書館デジタルコレクションから分割ダウンロードしたPDFや画像を、まとめて読みやすいPDFやEPUBにするためのデスクトップアプリです。

PDFや画像を追加して並び替え、必要な範囲を切り抜き、電子書籍リーダー向けに圧縮して出力できます。

## できること

- 複数PDF / 画像の結合と並び替え
- シングルページモード / 2ページモードでの切り抜き
- カラー、グレースケール、白黒二極化
- PDF / EPUB出力
- EPUBの左綴じ / 右綴じ指定
- OCRテキストの埋め込み

## パッケージバージョン

### ダウンロード

[最新のリリース](https://github.com/h1toiui/pdf-snipper-for-ndl/releases/latest

Windows Defender SmartScreenにより実行がブロックされる場合は、詳細情報 > 実行をクリックしてください。

## ソースコードからの実行

### 本体のセットアップ

Python 3.12で動作確認しています。

```bash
# Mac
cd pdf-snipper-for-ndl
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

```powershell
# Windows
cd pdf-snipper-for-ndl
py -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### OCRのセットアップ

OCRを使う場合は、別途セットアップが必要です。

アプリケーションと同じディレクトリでコマンドを実行し、NDLOCR-Liteをインストールしてください。

```bash
# Mac
python3 -m venv .venv-ndlocr
.venv-ndlocr/bin/python -m pip install git+https://github.com/ndl-lab/ndlocr-lite.git
```

```powershell
# Windows
py -m venv .venv-ndlocr
.venv-ndlocr\Scripts\python.exe -m pip install git+https://github.com/ndl-lab/ndlocr-lite.git
```

### 起動

```bash
python main.py
```

## 使い方

1. `PDF / 画像を追加` でPDFまたは画像を追加します。
2. 必要ならリストをドラッグして順番を変えます。
3. `シングルページ` または `2ページ` と、切り抜き枠のアスペクト比を選びます。
4. 必要ならプレビュー下部の `前へ` `次へ` で確認するページを移動します。
5. 枠内部のドラッグで位置を調整し、枠上のハンドラーで大きさを調整します。
6. 出力形式、画質、ファイル名、著者を確認します。
7. OCRが必要なら `OCR` を有効にします。
8. `実行` を押して保存先を選びます。

## 補足

- PDFは汎用的なファイル形式で、EPUBは電子書籍用のファイル形式です。EPUBファイルにはページ送り方向を埋め込むことができます。
- PDFで出力した場合、一般的なリーダーでは上下スクロールまたは左から右のページ送りでの閲覧となります。縦書き書籍のPDFを右から左のページ送りで閲覧するには専用のアプリ（SideBooks: [Android](https://play.google.com/store/apps/details?id=jp.co.tokyo_ip.SideBooks) / [iOS](http://itunes.apple.com/jp/app/id409777225) など）の使用を併せておすすめします。
- PDF, EPUBのどちらも[Send to Kindle](https://www.amazon.co.jp/sendtokindle)を使用することでKindleのクラウドにアップロードし、ログインしたそれぞれのデバイスで閲覧することができます[^1]。ただし現時点では、PDFは右から左のページ送りに対応していません。ページ送り方向を設定したEPUBはそのとおり閲覧できます。

[^1]: 厳密には、内部的にKindle形式へと変換されます。

## 注意

- 著作権および国立国会図書館など他サービスの利用規約を遵守してください。
- 著作物の複製（本アプリでの加工を含む）は私的利用においてのみ許可されています。
