FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Create data directory for SQLite
RUN mkdir -p /app/data

ENV DB_PATH=/app/data/jobscout.db
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Gunicorn with preload so background thread starts once
# Workers=1 is intentional: background scraper thread must be singleton
# Timeout=120 for long-running scrape-triggered requests
WORKDIR /app/backend
CMD ["gunicorn", "server:app", \
     "--bind", "0.0.0.0:10000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--preload"]
