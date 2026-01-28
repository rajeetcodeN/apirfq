# Use official slim Python image
FROM python:3.9-slim

# Install minimal system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*
    
# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Environment variables for Python
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY python/ .

# Expose port (Render sets $PORT env var, but we document default)
EXPOSE 8000

# Start Command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
