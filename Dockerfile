FROM python:3.13-slim

# OpenCV (used by pdf2docx for table detection) needs glib at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py LICENSE README.md ./

ENV PYTHONUNBUFFERED=1
# One conversion at a time per instance: pdf2docx is CPU and memory heavy;
# Cloud Run adds instances for concurrent requests.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 1 --timeout 540 main:app
