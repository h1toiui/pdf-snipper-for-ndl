import cv2
import fitz
import numpy as np

from models import IMAGE_PROCESS_ENHANCE, IMAGE_PROCESS_NONE

# 白黒二極化の調整値。紙地の黒ドットが出る場合は、まずここを調整する。
# 1. グレースケール化
# 2. ページ内の明るい側 84% 点を「紙色」として推定
# 3. その紙色が 230 になるように全体を明るくする
# 4. 固定しきい値 170 で二値化

PAPER_WHITE_PERCENTILE = 84
TARGET_PAPER_WHITE = 230
BINARY_THRESHOLD = 170


def apply_image_processing(pixmap: fitz.Pixmap, mode: str) -> fitz.Pixmap:
    """UIで選ばれた画像処理モードをPixmapへ適用する入口。"""
    if mode == IMAGE_PROCESS_NONE:
        return pixmap
    if mode == IMAGE_PROCESS_ENHANCE:
        return enhance_for_ereader(pixmap)

    raise ValueError(f"Unsupported image processing mode: {mode}")


def enhance_for_ereader(pixmap: fitz.Pixmap) -> fitz.Pixmap:
    """電子リーダーで読みやすい白背景・黒文字の2値画像に寄せる。"""
    # 以降の処理は濃淡だけを見ればよいので、最初にグレースケールへ揃える。
    gray = _pixmap_to_gray_array(pixmap)

    # 紙色を白側へ寄せてから二値化する。
    brightened = _brighten_paper(gray)

    # 白黒へ二極化する。出力サイズも小さくなりやすい。
    binary = _binarize(brightened)
    return _gray_array_to_pixmap(binary)


def _pixmap_to_gray_array(pixmap: fitz.Pixmap):
    """PyMuPDFのPixmapをOpenCVで扱えるグレースケール配列へ変換する。"""
    data = np.frombuffer(pixmap.samples, dtype=np.uint8)

    if pixmap.n == 1:
        return data.reshape(pixmap.height, pixmap.width).copy()

    image = data.reshape(pixmap.height, pixmap.width, pixmap.n)

    # OpenCVのRGB変換前にアルファチャンネルは落とす。
    if pixmap.alpha:
        image = image[:, :, :-1]

    if image.shape[2] == 1:
        return image[:, :, 0].copy()
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def _brighten_paper(gray):
    """推定した紙色が目標の白さになるよう、二値化前に明るくする。"""
    estimated_paper = np.percentile(gray, PAPER_WHITE_PERCENTILE)
    bias = max(0, TARGET_PAPER_WHITE - estimated_paper)
    brightened = gray.astype(np.float32) + bias
    return np.clip(brightened, 0, 255).astype(np.uint8)


def _binarize(gray):
    """背景補正後の明るさを固定しきい値で白黒へ分ける。"""
    _, binary = cv2.threshold(
        gray,
        BINARY_THRESHOLD,
        255,
        cv2.THRESH_BINARY,
    )
    return binary


def _gray_array_to_pixmap(gray):
    """OpenCVの配列をPNG経由でPyMuPDFのPixmapへ戻す。"""
    ok, buffer = cv2.imencode(".png", gray)
    if not ok:
        raise ValueError("Failed to encode enhanced image")
    return fitz.Pixmap(buffer.tobytes())
