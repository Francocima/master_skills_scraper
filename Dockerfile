# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create results directory
RUN mkdir -p results

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application
CMD ["python", "seek_scraper_BS_v3.py"]