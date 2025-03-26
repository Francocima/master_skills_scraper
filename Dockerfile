# Use a minimal Python base image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# Install ChromeDriver
RUN CHROME_DRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE) \
    && wget -N http://chromedriver.storage.googleapis.com/$CHROME_DRIVER_VERSION/chromedriver_linux64.zip -P ~/tmp \
    && unzip ~/tmp/chromedriver_linux64.zip -d ~/tmp \
    && mv ~/tmp/chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver
# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    selenium \
    webdriver-manager \
    # Add any other required Python packages
    requests

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Command to run the application
CMD ["uvicorn", "seek_scraper_BS_v7:app", "--host", "0.0.0.0", "--port", "8080"]



