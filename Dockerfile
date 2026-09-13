FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root system user for security hardening
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Copy application source code
COPY . .
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose webhook port
EXPOSE 8000

# Run entrypoint
CMD ["python", "main.py"]
