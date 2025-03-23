FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install  -r requirements.txt

# Copy application code
COPY ./app/ .

# Environment variables
ENV PORT=8082 \
    CONSUL_HOST=medapp-consul \
    CONSUL_PORT=8500 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

# Expose port
EXPOSE ${PORT}

# Start the service
CMD ["python", "app.py"]