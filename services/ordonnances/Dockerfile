FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY ./app/ .

# Environment variables
ENV PORT=8082 \
    METRICS_PORT=9092 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH" 

# Expose ports
EXPOSE ${PORT}
EXPOSE ${METRICS_PORT}

# Start the service with proper logging
CMD ["python", "app.py"]