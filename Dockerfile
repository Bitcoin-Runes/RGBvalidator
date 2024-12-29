FROM python:3.11-slim

# Install system dependencies including Rust
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . $HOME/.cargo/env \
    && rustup target add x86_64-unknown-linux-gnu

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/root/.cargo/bin:${PATH}"

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /app/data/wallets /app/data/backups /app/logs

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Create volume mount points
VOLUME ["/app/data", "/app/logs"]

# Run the application
CMD ["python", "-m", "validator"] 