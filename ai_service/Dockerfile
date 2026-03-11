FROM python:3.11-slim
WORKDIR /app

# Install build dependencies for pandas/scikit-learn
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install deps first
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 -r requirements.txt

COPY . .
EXPOSE 8000

# --reload: uvicorn restarts automatically when you edit a .py file
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]