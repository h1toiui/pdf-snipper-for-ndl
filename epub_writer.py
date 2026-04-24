import uuid
import zipfile
from datetime import datetime
from html import escape

import fitz


def save_as_epub(path, images, title, direction):
    """画像リストをEPUB 3.0形式で保存する"""
    pub_id = str(uuid.uuid4())
    mod_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = escape(title)

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

            html_content = _page_xhtml(i, img_name, width, height)
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

        opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="pub-id" version="3.0" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{pub_id}</dc:identifier>
    <dc:title>{safe_title}</dc:title>
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
</package>'''
        zf.writestr("OEBPS/content.opf", opf)

        ncx = f'''<?xml version="1.0" encoding="UTF-8"?>
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
</ncx>'''
        zf.writestr("OEBPS/toc.ncx", ncx)


def _image_size(image_data):
    pixmap = fitz.Pixmap(image_data)
    return pixmap.width, pixmap.height


def _page_xhtml(index, img_name, width, height):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
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
    svg {{
      display: block;
      width: 100%;
      height: 100%;
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
</body>
</html>'''


def _nav_xhtml(title):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
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
</html>'''
