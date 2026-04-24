import uuid
import zipfile
from datetime import datetime


def save_as_epub(path, images, title, direction):
    """画像リストをEPUB 3.0形式で保存する"""
    pub_id = str(uuid.uuid4())
    mod_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

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
            img_name = f"img_{i:04d}.png"
            html_name = f"page_{i:04d}.xhtml"
            zf.writestr(f"OEBPS/Images/{img_name}", img_data)

            html_content = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<!DOCTYPE html>"
                '<html xmlns="http://www.w3.org/1999/xhtml">'
                "<head>"
                f"<title>{i}</title>"
                "<style>"
                "body {margin:0;padding:0;background-color:#fff;} "
                "img {width:100%;height:auto;}"
                "</style>"
                "</head>"
                f'<body><img src="../Images/{img_name}" /></body>'
                "</html>"
            )
            zf.writestr(f"OEBPS/Text/{html_name}", html_content)

            manifest_items.append(
                f'<item id="img{i}" href="Images/{img_name}" media-type="image/png"/>'
            )
            manifest_items.append(
                f'<item id="page{i}" href="Text/{html_name}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="page{i}"/>')

        opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="pub-id" version="3.0" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">{pub_id}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>ja</dc:language>
    <meta property="dcterms:modified">{mod_time}</meta>
  </metadata>
  <manifest>
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
  <docTitle><text>{title}</text></docTitle>
  <navMap>
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>Start</text></navLabel>
      <content src="Text/page_0000.xhtml"/>
    </navPoint>
  </navMap>
</ncx>'''
        zf.writestr("OEBPS/toc.ncx", ncx)
