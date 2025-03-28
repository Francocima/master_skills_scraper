# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install essential diagnostic tools
RUN apt-get update && apt-get install -y \
    bash \
    wget \
    curl \
    gnupg \
    unzip \
    file \
    # Chrome dependencies
    libx11-6 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libgbm1 \
    libatk1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Comprehensive system and Chrome diagnostic information
RUN echo "System Information:" \
    && uname -a \
    && echo "\nArchitecture:" \
    && uname -m \
    && echo "\nCPU Info:" \
    && cat /proc/cpuinfo | grep "model name" | uniq

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver with explicit version
RUN CHROME_DRIVER_VERSION=134.0.6998.165 \
    && CHROMEDRIVER_URL="https://storage.googleapis.com/chrome-for-testing-public/${CHROME_DRIVER_VERSION}/linux64/chromedriver-linux64.zip" \
    && echo "Downloading ChromeDriver from: $CHROMEDRIVER_URL" \
    && wget -v "$CHROMEDRIVER_URL" -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /opt/ \
    && chmod +x /opt/chromedriver-linux64/chromedriver \
    && ln -s /opt/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && chromedriver --version

# Set the working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run command
CMD ["uvicorn", "seek_scraper_BS_v7:app", "--host", "0.0.0.0", "--port", "8080"]




