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

# Create log directory with appropriate permissions
RUN mkdir -p /app/logs && \
    chmod 777 /app/logs

# Environment variables
ENV PORT=8085 \
    METRICS_PORT=9095 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH" \
    LOG_PATH="/app/logs"

# Make sure log directory persists
VOLUME ["/app/logs"]

# Expose ports
EXPOSE ${PORT}
EXPOSE ${METRICS_PORT}

# Start the service with proper logging
CMD ["sh", "-c", "python app.py 2>&1 | tee -a /app/logs/reports.log"]