# Dockerfile for CodeReview Agent

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy Python source
COPY python/src /app/src
COPY python/pyproject.toml /app/
COPY python/README.md /app/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 codereview && \
    chown -R codereview:codereview /app

USER codereview

# Default command
ENTRYPOINT ["python", "-m", "codereview.cli"]

# Default args
CMD ["--help"]
