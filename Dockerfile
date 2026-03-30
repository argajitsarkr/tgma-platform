FROM python:3.12-slim

# System dependencies for WeasyPrint and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create upload directory
RUN mkdir -p /data/uploads

# Set environment
ENV FLASK_APP=wsgi.py
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run with Gunicorn (4 workers is plenty for 5 users on 84 GB RAM)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "wsgi:app"]
