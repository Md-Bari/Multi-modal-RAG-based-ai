FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Set workspace directory
WORKDIR /app

# Copy requirements file first for better caching
COPY Django/requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy Django source files
COPY Django/Multi_Model_AI/ /app/

# Copy entrypoint script
COPY entrypoint.py /app/

# Expose Django port
EXPOSE 8000

# Set entrypoint and default command
ENTRYPOINT ["python", "/app/entrypoint.py"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
