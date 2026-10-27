"""PDF -> Word (.docx) conversion service for Docuimza.

A private Cloud Run service: only the project's Cloud Functions service
account may call it (the function checks the user, PRO and quotas first).

    POST /convert   body: the PDF bytes (application/pdf)
        200  the .docx
        400  {"error": "not_pdf" | "encrypted" | "empty"}
        413  {"error": "too_large" | "too_many_pages"}
        422  {"error": "scanned"}   pages are pictures; OCR them first
        500  {"error": "converter_failed"}
    GET  /          health check

Layout reconstruction is pdf2docx (MIT) on PyMuPDF (AGPL-3.0), so this
service is AGPL-3.0 as well; see LICENSE and README.md.
"""

import io
import logging
import os
import tempfile

import pymupdf
from docx import Document
from docx.oxml.ns import qn
from flask import Flask, Response, jsonify, request
from pdf2docx import Converter

MAX_BYTES = int(os.environ.get("MAX_BYTES", 25 * 1024 * 1024))
MAX_PAGES = int(os.environ.get("MAX_PAGES", 100))
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Bullets set in Symbol/Wingdings arrive as private-use characters that no
# ordinary font draws; Word would show empty boxes.
BULLETS = {
    "\uf0b7": "\u2022",  # Symbol bullet
    "\uf0a7": "\u25aa",  # Wingdings small square
    "\uf06e": "\u25a0",  # Wingdings black square
    "\uf0d8": "\u27a2",  # Wingdings arrowhead
    "\uf076": "\u2756",  # Wingdings diamond
    "\uf0fc": "\u2713",  # Wingdings check
    "\uf0a8": "\u25a1",  # Wingdings white square
    "\uf06f": "\u25cb",  # Wingdings circle
    "\uf02d": "\u2013",  # Symbol dash
    "\uf0e0": "\u2192",  # Symbol arrow
}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


class Refused(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


def check(pdf: bytes) -> None:
    """Refuses what the converter cannot turn into a useful document."""
    if not pdf:
        raise Refused(400, "empty")
    if len(pdf) > MAX_BYTES:
        raise Refused(413, "too_large")
    if not pdf.startswith(b"%PDF-"):
        raise Refused(400, "not_pdf")
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception:
        raise Refused(400, "not_pdf")
    with doc:
        if doc.needs_pass:
            raise Refused(400, "encrypted")
        if doc.page_count == 0:
            raise Refused(400, "empty")
        if doc.page_count > MAX_PAGES:
            raise Refused(413, "too_many_pages")
        if is_scanned(doc):
            raise Refused(422, "scanned")


def is_scanned(doc) -> bool:
    """True when the pages are pictures: no visible text, or only the
    invisible text an OCR layer puts over a scan."""
    visible = 0
    for page in doc:
        for span in page.get_texttrace():
            # Render mode 3 is invisible text (an OCR layer).
            if span.get("type") != 3:
                visible += len(span.get("chars", ()))
        if visible >= 50:
            return False
    return visible < 50


def fix_bullets(docx_bytes: bytes) -> bytes:
    """Maps private-use bullet characters to their Unicode look-alikes and
    sets those runs in an ordinary font."""
    document = Document(io.BytesIO(docx_bytes))
    changed = False

    def runs():
        for p in document.paragraphs:
            yield from p.runs
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        yield from p.runs

    for run in runs():
        text = run.text
        if not any(c in BULLETS for c in text):
            continue
        run.text = "".join(BULLETS.get(c, c) for c in text)
        fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            fonts.set(qn(attr), "Arial")
        changed = True

    if not changed:
        return docx_bytes
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def convert(pdf: bytes) -> bytes:
    check(pdf)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.pdf")
        dst = os.path.join(tmp, "out.docx")
        with open(src, "wb") as f:
            f.write(pdf)
        cv = Converter(src)
        try:
            cv.convert(dst, multi_processing=False)
        finally:
            cv.close()
        with open(dst, "rb") as f:
            docx_bytes = f.read()
    if not docx_bytes.startswith(b"PK"):
        raise RuntimeError("converter produced no docx")
    return fix_bullets(docx_bytes)


@app.get("/")
def health():
    return jsonify(status="ok")


@app.post("/convert")
def convert_route():
    try:
        docx_bytes = convert(request.get_data(cache=False))
    except Refused as e:
        return jsonify(error=e.code), e.status
    except Exception:
        logging.exception("conversion failed")
        return jsonify(error="converter_failed"), 500
    return Response(docx_bytes, mimetype=DOCX_MIME)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8768)))
