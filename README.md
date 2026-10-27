# PDF → Word service

Turns a PDF with real text into an editable `.docx` that keeps the layout:
columns, tables, pictures, headings and links. Built on
[pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) (MIT) and
[PyMuPDF](https://github.com/pymupdf/PyMuPDF) (AGPL-3.0).

Docuimza calls it from the `convertToDocx` Cloud Function, which checks the
user, PRO status and quotas first. The service runs on Cloud Run with no
public access: only the functions' service account may invoke it.

## API

`POST /convert` with the PDF as the request body.

| Status | Body | Meaning |
|---|---|---|
| 200 | the `.docx` | converted |
| 400 | `{"error": "not_pdf" \| "encrypted" \| "empty"}` | not something to convert |
| 413 | `{"error": "too_large" \| "too_many_pages"}` | over 25 MB or 100 pages |
| 422 | `{"error": "scanned"}` | the pages are pictures; OCR them first |
| 500 | `{"error": "converter_failed"}` | the converter gave up |

Scanned pages (also with an invisible OCR text layer) are refused rather
than turned into a broken document.

Bullets drawn with Symbol or Wingdings come out of the converter as
private-use characters that show as empty boxes in Word; they are mapped to
their Unicode look-alikes.

## Run and test locally

```
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # .venv/bin/pip on macOS/Linux
.venv/Scripts/python -m unittest test_main
.venv/Scripts/python main.py                    # http://127.0.0.1:8768
```

The Firebase emulator test (`functions/test/emulator.convert.mjs`) talks to
this local server when `PDF2DOCX_URL=http://127.0.0.1:8768` and
`PDF2DOCX_AUTH=none` are set in `functions/.env.local`.

## Deploy

The image is built by GitHub Actions (`.github/workflows/docker.yml`) and
published on Docker Hub as `<user>/docuimza-pdf2docx`; Cloud Run pulls it
from there, so no image is built or stored on Google Cloud.

```
gcloud run deploy pdf2docx --image docker.io/<user>/docuimza-pdf2docx:<tag> \
  --region us-central1 --no-allow-unauthenticated --cpu 1 --memory 2Gi \
  --concurrency 1 --timeout 540 --min-instances 0 --max-instances 2
gcloud run services add-iam-policy-binding pdf2docx --region us-central1 \
  --member serviceAccount:<project-number>-compute@developer.gserviceaccount.com \
  --role roles/run.invoker
```

Then set `PDF2DOCX_URL` in `functions/.env` and turn on Remote Config
`pdf_to_word_enabled`.

## License

AGPL-3.0-or-later (see `LICENSE`), because of PyMuPDF. The source of the
running service is this folder; it is published so that everyone who uses
the conversion through Docuimza can get it.
