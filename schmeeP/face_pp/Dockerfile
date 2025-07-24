# Use a base image with Python pre-installed
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system-level dependencies for face_recognition and opencv-python
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    zlib1g-dev \
    libgl1-mesa-glx \
    libxkbcommon-x11-0 \
    libxcb-randr0 \
    libxcb-xinerama0 \
    libfontconfig1 \
    libxrender1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    mysql-connector-python \
    paho-mqtt \
    numpy \
    python-dotenv \
    mtcnn \
    opencv-python \
    face-recognition \
    scikit-learn \
    tensorflow # ADDED THIS LINE
    # Note: Depending on your specific hardware (e.g., GPU), you might need tensorflow-gpu
    # but for a general CPU setup, 'tensorflow' is sufficient.

# Copy all your application files into the container
COPY . .

# You don't need a CMD here as different services will run different commands
