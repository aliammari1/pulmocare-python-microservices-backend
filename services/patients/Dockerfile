FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get -y update && \
    apt-get install -y --no-install-recommends \
    curl \

    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY ./app/ .

# Create log directory with appropriate permissions
RUN mkdir -p /var/log/medapp/patients && \
    chmod 777 /var/log/medapp/patients

# Environment variables
ENV PORT=8083 \
    METRICS_PORT=9093 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH" \
    LOG_PATH="/app/logs"

# Expose ports
EXPOSE ${PORT}
EXPOSE ${METRICS_PORT}

# Start the service with proper logging
CMD ["python", "app.py"]