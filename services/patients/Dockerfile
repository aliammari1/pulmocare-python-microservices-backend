FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get -y update
RUN apt-get install -y --fix-missing \
    build-essential \
    cmake \
    gfortran \
    git \
    wget \
    curl \
    graphicsmagick \
    libgraphicsmagick1-dev \
    libatlas-base-dev \
    libavcodec-dev \
    libavformat-dev \
    libgtk2.0-dev \
    libjpeg-dev \
    liblapack-dev \
    libswscale-dev \
    pkg-config \
    software-properties-common \
    zip \
    && apt-get clean && rm -rf /tmp/* /var/tmp/*

# RUN cd ~ && \
#     mkdir -p dlib && \
#     git clone -b 'v19.9' --single-branch https://github.com/davisking/dlib.git dlib/ && \
#     cd  dlib/ && \
#     python3 setup.py install --yes USE_AVX_INSTRUCTIONS


# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install  -r requirements.txt

# Copy application code
COPY ./app/ .

# Environment variables
ENV PORT=8081 \
    CONSUL_HOST=medapp-consul \
    CONSUL_PORT=8500 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH"

# Expose port
EXPOSE ${PORT}

# Start the service
CMD ["python", "app.py"]