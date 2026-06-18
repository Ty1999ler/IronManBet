FROM python:3.13-slim

WORKDIR /app

# Install dependencies first so they cache across code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY main.py database.py ./
COPY static ./static

# SQLite database lives here; mount a volume at /data to persist it
ENV IRONMAN_DB=/data/ironman.db
VOLUME ["/data"]

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
