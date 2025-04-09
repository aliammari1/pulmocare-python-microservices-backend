FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including curl for health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install wheel setuptools && \
    pip install -r requirements.txt

# Copy application code
COPY ./app/ .

# Environment variables
ENV PORT=8086 \
    METRICS_PORT=9096 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH"

# Expose ports
EXPOSE ${PORT}
EXPOSE ${METRICS_PORT}

# Start the service with proper logging
CMD ["python", "app.py"]