# Use Python 3.11 slim as base
FROM python:3.11-slim-bullseye

# Set build arguments
ARG USER=validator
ARG USER_ID=1000
ARG GROUP_ID=1000

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/home/${USER}/.local/bin:${PATH}" \
    VIRTUAL_ENV="/home/${USER}/venv"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libssl-dev \
    git \
    gcc \
    g++ \
    make \
    cmake \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -g ${GROUP_ID} ${USER} && \
    useradd -m -u ${USER_ID} -g ${USER} -s /bin/bash ${USER}

# Create necessary directories
RUN mkdir -p /app/data/wallets /app/data/backups /app/logs && \
    chown -R ${USER}:${USER} /app

# Switch to non-root user
USER ${USER}
WORKDIR /app

# Set up Python virtual environment
RUN python -m venv ${VIRTUAL_ENV}
ENV PATH="${VIRTUAL_ENV}/bin:$PATH"

# Install Python dependencies
COPY --chown=${USER}:${USER} requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=${USER}:${USER} . .

# Create volume mount points
VOLUME ["/app/data", "/app/logs"]

# Expose ports
EXPOSE 5000 18443

# Set default command
ENTRYPOINT ["python", "-m"]
CMD ["validator"] 