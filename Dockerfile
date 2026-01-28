# Use official slim Python image
FROM python:3.9-slim

# Install system dependencies (build tools)
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Spacy Model during build (CRITICALLY IMPORTANT FOR STARTUP SPEED)
# This prevents downloading 500MB+ on every cold start
RUN python -m spacy download de_core_news_sm

# Copy application code
COPY python/ .

# Expose port (Render sets $PORT env var, but we document default)
EXPOSE 8000

# Start Command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
