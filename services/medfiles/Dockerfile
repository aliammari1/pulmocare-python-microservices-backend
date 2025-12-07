FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends \
    curl \
    gcc \
    build-essential \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install wheel setuptools && \
    pip install -r requirements.txt

# Copy application code
COPY ./app/ .

# Environment variables
ENV PORT=8088 \
    METRICS_PORT=9088 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH"

# Expose ports
EXPOSE ${PORT}
EXPOSE ${METRICS_PORT}

# Start the service with proper logging
CMD ["python", "app.py"]
