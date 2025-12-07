# Use NVIDIA's CUDA-enabled Python image as base
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    build-essential \
    wget \
    curl \
    git \
    libsndfile1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN pip3 install -e .

# Install additional dependencies that might be needed by medical imaging tools
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
RUN pip3 install gradio transformers

# Create directories for models and temp files
RUN mkdir -p /app/model-weights /app/temp /app/logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=8087
ENV MODEL_PATH=/app/models
ENV CUDA_VISIBLE_DEVICES=0

# Copy application code
COPY . .

# Allow the app to create files in these directories
RUN chmod -R 777 /app/model-weights /app/temp /app/logs

# Expose port that the application will run on
EXPOSE 8585

# Command to run the application
CMD ["python", "main.py"]