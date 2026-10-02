"""Small image-report DOCX writer using the standard OOXML zip format."""

from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


class Document:
    def __init__(self):
        self.parts = []
        self.images = []

    def add_heading(self, text, level=1):
        self.add_paragraph(text)

    def add_paragraph(self, text):
        self.parts.append(
            '<w:p><w:r><w:t xml:space="preserve">' + escape(str(text)) + "</w:t></w:r></w:p>"
        )

    def add_picture(self, stream, width=6):
        from PIL import Image

        image = Image.open(stream)
        cx = int(width * 914400)
        cy = int(cx * image.height / image.width)
        stream.seek(0)
        self.images.append(stream.read())
        i = len(self.images)
        self.parts.append(
            f'<w:p><w:r><w:drawing><wp:inline><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{i}" name="Image {i}"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="{i}" name="Image {i}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId{i}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
        )

    def save(self, path):
        relationships = "http://schemas.openxmlformats.org/package/2006/relationships"
        ns = "http://schemas.openxmlformats.org/"
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                f'<Types xmlns="{ns}package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
            )
            archive.writestr(
                "_rels/.rels",
                f'<Relationships xmlns="{relationships}"><Relationship Id="rId1" Type="{ns}officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
            )
            body = "".join(self.parts)
            archive.writestr(
                "word/document.xml",
                f'<w:document xmlns:w="{ns}wordprocessingml/2006/main" xmlns:r="{ns}officeDocument/2006/relationships" xmlns:wp="{ns}drawingml/2006/wordprocessingDrawing" xmlns:a="{ns}drawingml/2006/main" xmlns:pic="{ns}drawingml/2006/picture"><w:body>{body}<w:sectPr/></w:body></w:document>',
            )
            links = "".join(
                f'<Relationship Id="rId{i}" Type="{ns}officeDocument/2006/relationships/image" Target="media/image{i}.png"/>'
                for i in range(1, len(self.images) + 1)
            )
            archive.writestr(
                "word/_rels/document.xml.rels",
                f'<Relationships xmlns="{relationships}">{links}</Relationships>',
            )
            for i, data in enumerate(self.images, 1):
                archive.writestr(f"word/media/image{i}.png", data)
