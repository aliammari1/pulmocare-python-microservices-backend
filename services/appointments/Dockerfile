FROM python:3.11-slim

WORKDIR /app

# Install required packages
RUN apt-get update && \
    apt-get install -y gcc curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY app/ .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8087/health || exit 1

# Run the application
CMD ["python", "app.py"]

EXPOSE 8087