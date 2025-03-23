FROM python:3.11-slim

WORKDIR /app

# Cài đặt dependencies hệ thống cho Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-4-0 \
    libgraphene-1.0-0 \
    libgstreamer1.0-0 \
    libgstreamer-gl1.0-0 \
    libgstreamer-codecparsers-1.0-0 \
    libavif-0.9-0 \
    libenchant-2-2 \
    libsecret-1-0 \
    libmanette-0.2-0 \
    libgles2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Sao chép requirements.txt và cài đặt dependencies Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cài đặt Playwright và browsers
RUN playwright install --with-deps chromium

# Sao chép code vào container
COPY . .

# Thiết lập biến môi trường
ENV PYTHONUNBUFFERED=1

# Lệnh khởi động
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
