FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY ../../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ingestion service
COPY . .

# Run ingestion
CMD ["python", "ingest.py"]