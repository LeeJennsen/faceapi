# face-data-sim/Dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "face-data-sub.py"]

