FROM python:3.11-slim

WORKDIR /app

# Copy semua file
COPY . .

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic

# Expose port
EXPOSE 8000

# Jalankan
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
