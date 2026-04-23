# PDF Snipper For NDL

国立国会図書館（NDL） デジタルコレクションからは、最大100コマまでしかダウンロードできません。  
この分割されたPDFを、GUIを使って**結合・並び替え・切り抜き・圧縮**し、電子書籍アプリ / 端末で閲覧できるようにします。

## 機能

- PDF結合 & 並び替え
- 2ページ同時切り抜き: 1ページ目と2ページ目の範囲をマウスドラッグで指定
- 出力カスタマイズ: カラー / グレースケールの選択、圧縮レベル

## セットアップ

### 環境
* macOS (Intel / Apple Silicon)
* Python 3.11以上

### 仮想環境の構築とライブラリのインストール

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
