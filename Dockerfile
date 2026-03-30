FROM python:3.12-slim

# System dependencies for psycopg2
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN grep -v WeasyPrint requirements.txt > reqs.txt \
    && pip install --no-cache-dir -r reqs.txt \
    && rm reqs.txt

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
