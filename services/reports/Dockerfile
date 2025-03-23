FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install setuptools wheel && \
    pip install -r requirements.txt && \
    pip install gunicorn

# Copy application code
COPY . .

# Create directory for exported files
RUN mkdir -p /tmp/exports && \
    chmod 777 /tmp/exports

# Environment variables
ENV PORT=8085 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/app:$PYTHONPATH" \
    PDF_EXPORT_PATH="/tmp/exports"

# Expose ports
EXPOSE ${PORT}
EXPOSE 9090

# Start both the main service and consumer
CMD ["sh", "-c", "python consumer.py & python app.py"]