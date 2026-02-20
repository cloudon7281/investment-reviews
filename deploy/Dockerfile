FROM python:3.13-slim

# Keep image minimal; no runtime apt installs expected.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Ensure a writable working directory for uid 1000 runs
RUN mkdir -p /app/logs /app/outputs /app/history && chmod -R 0777 /app/logs /app/outputs /app/history

# System deps (if any future libs need them). Keep empty for now.
# RUN apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Default (overridden in compose)
CMD ["python","/app/update_google_sheet.py"]
