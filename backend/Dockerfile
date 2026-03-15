# Sử dụng Python phiên bản slim để giảm dung lượng Image
FROM python:3.10-slim

# Thiết lập biến môi trường để Python không tạo file .pyc và log xuất hiện ngay lập tức
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cài đặt các thư viện hệ thống cần thiết
# 1. tesseract-ocr & libtesseract-dev: Để xử lý ảnh (OCR)
# 2. libpq-dev & gcc: Để biên dịch thư viện psycopg2 (kết nối Postgres)
# 3. poppler-utils: Hỗ trợ xử lý PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    libpq-dev \
    gcc \
    g++ \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Thiết lập thư mục làm việc trong Container
WORKDIR /app

# Copy file requirements vào trước để tận dụng Docker Cache
COPY requirements.txt .

# Nâng cấp pip và cài đặt các thư viện Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn vào Container
COPY . .

# Tạo thư mục chứa Vector Store để tránh lỗi quyền truy cập
RUN mkdir -p /app/vector_stores && chmod 777 /app/vector_stores

# Cổng mặc định của FastAPI
EXPOSE 8000

# Lệnh khởi chạy Server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]