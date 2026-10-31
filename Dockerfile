FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
COPY data ./data
COPY scripts/refresh.py ./scripts/refresh.py

EXPOSE 8000
# Refresh the forecast on start (falls back to the committed snapshot if it fails), then serve.
CMD ["sh", "-c", "python scripts/refresh.py || echo 'refresh failed, serving last snapshot'; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
