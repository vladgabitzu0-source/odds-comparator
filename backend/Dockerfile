FROM python:3.11-slim

# Don't buffer stdout/stderr, so print()/tracebacks show up in Railway logs
# immediately instead of being held in a buffer (and sometimes lost).
ENV PYTHONUNBUFFERED=1

# Install Chromium dependencies for Playwright
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install chromium

COPY . .

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
