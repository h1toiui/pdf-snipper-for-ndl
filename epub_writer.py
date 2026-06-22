import uuid
import zipfile
from datetime import datetime
from html import escape

import fitz


def save_as_epub(path, images, title, direction, ocr_pages=None, author=""):
    """画像リストと書誌情報をEPUB 3.0形式で保存する。"""
    pub_id = str(uuid.uuid4())
    mod_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = escape(title)
    safe_author = escape(author.strip())
    creator_meta = (
        f"\n    <dc:creator>{safe_author}</dc:creator>" if safe_author else ""
    )
    ocr_pages = ocr_pages or []

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "mimetype",
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )

        container = (
            '<?xml version="1.0"?>'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            "<rootfiles>"
            '<rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/>'
            "</rootfiles>"
            "</container>"
        )
        zf.writestr("META-INF/container.xml", container)

        manifest_items = []
        spine_items = []
        for i, img_data in enumerate(images):
            width, height = _image_size(img_data)
            img_name = f"img_{i:04d}.png"
            html_name = f"page_{i:04d}.xhtml"
            zf.writestr(f"OEBPS/Images/{img_name}", img_data)

            ocr_page = ocr_pages[i] if i < len(ocr_pages) else None
            html_content = _page_xhtml(i, img_name, width, height, ocr_page)
            zf.writestr(f"OEBPS/Text/{html_name}", html_content)

            manifest_items.append(
                f'<item id="img{i}" href="Images/{img_name}" media-type="image/png"/>'
            )
            manifest_items.append(
                f'<item id="page{i}" href="Text/{html_name}" media-type="application/xhtml+xml" properties="svg"/>'
            )
            spine_items.append(f'<itemref idref="page{i}"/>')

        nav = _nav_xhtml(safe_title)
        zf.writestr("OEBPS/nav.xhtml", nav)

        opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="pub-id" version="3.0" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{pub_id}</dc:identifier>
    <dc:title>{safe_title}</dc:title>{creator_meta}
    <dc:language>ja</dc:language>
    <meta property="dcterms:modified">{mod_time}</meta>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">none</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {''.join(manifest_items)}
  </manifest>
  <spine toc="toc" page-progression-direction="{direction}">
    {''.join(spine_items)}
  </spine>
</package>"""
        zf.writestr("OEBPS/content.opf", opf)

        ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{pub_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{safe_title}</text></docTitle>
  <navMap>
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>Start</text></navLabel>
      <content src="Text/page_0000.xhtml"/>
    </navPoint>
  </navMap>
</ncx>"""
        zf.writestr("OEBPS/toc.ncx", ncx)


def _image_size(image_data):
    """画像バイト列からEPUBページ用の幅と高さを取得する。"""
    pixmap = fitz.Pixmap(image_data)
    return pixmap.width, pixmap.height


def _page_xhtml(index, img_name, width, height, ocr_page=None):
    """1ページ分の画像とOCRレイヤーを含むXHTMLを作る。"""
    ocr_layer = _ocr_layer_xhtml(ocr_page, width, height)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{index}</title>
  <meta name="viewport" content="width={width}, height={height}"/>
  <style>
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      background: #fff;
      overflow: hidden;
    }}
    body {{
      position: relative;
    }}
    svg {{
      display: block;
      width: 100%;
      height: 100%;
    }}
    .ocr-layer {{
      position: absolute;
      left: 0;
      top: 0;
      width: {width}px;
      height: {height}px;
      pointer-events: none;
      user-select: text;
      opacity: 0.01;
    }}
    .ocr-line {{
      position: absolute;
      display: block;
      overflow: hidden;
      white-space: nowrap;
      line-height: 1;
      text-align: justify;
      text-align-last: justify;
      text-justify: inter-character;
    }}
    .ocr-line.vertical {{
      writing-mode: vertical-rl;
      text-orientation: mixed;
    }}
  </style>
</head>
<body>
  <svg xmlns="http://www.w3.org/2000/svg"
       xmlns:xlink="http://www.w3.org/1999/xlink"
       version="1.1"
       width="100%"
       height="100%"
       viewBox="0 0 {width} {height}"
       preserveAspectRatio="xMidYMid meet">
    <image width="{width}" height="{height}" href="../Images/{img_name}" xlink:href="../Images/{img_name}"/>
  </svg>
  {ocr_layer}
</body>
</html>"""


def _ocr_layer_xhtml(ocr_page, width, height):
    """OCR結果を画像上に重ねる透明な位置付きHTMLへ変換する。"""
    if ocr_page is None:
        return ""
    if not ocr_page.lines:
        if not ocr_page.text:
            return ""
        return (
            '<div class="ocr-layer">'
            f'<span class="ocr-line" style="left:0; top:0; width:1px; height:1px; font-size:1px;">'
            f"{escape(ocr_page.text)}</span></div>"
        )

    scale_x = width / max(1, ocr_page.image_width)
    scale_y = height / max(1, ocr_page.image_height)
    spans = []
    for line in ocr_page.lines:
        x = line.x0 * scale_x
        y = line.y0 * scale_y
        w = max(1, (line.x1 - line.x0) * scale_x)
        h = max(1, (line.y1 - line.y0) * scale_y)
        font_size = max(h, w) / len(line.text) or 1
        class_name = "ocr-line vertical" if line.is_vertical else "ocr-line"
        spans.append(
            f'<span class="{class_name}" style="left:{x:.2f}px; top:{y:.2f}px; '
            f'width:{w:.2f}px; height:{h:.2f}px; font-size:{font_size:.2f}px;">'
            f"{escape(line.text)}</span>"
        )

    return f'<div class="ocr-layer">{"".join(spans)}</div>'


def _nav_xhtml(title):
    """EPUB 3用の最小限のナビゲーションXHTMLを作る。"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{title}</title>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>{title}</h1>
    <ol>
      <li><a href="Text/page_0000.xhtml">Start</a></li>
    </ol>
  </nav>
</body>
</html>"""
