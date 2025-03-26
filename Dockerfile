# Use a minimal Python base image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install required system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Add Chrome's repository and install Google Chrome
RUN mkdir -p /etc/apt/keyrings && \
    wget -qO - https://dl.google.com/linux/linux_signing_key.pub | tee /etc/apt/keyrings/google-keyring.gpg > /dev/null && \
    echo "deb [signed-by=/etc/apt/keyrings/google-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" | tee /etc/apt/sources.list.d/google.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

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
CMD ["python", "seek_scraper_BS_v7.py"]

