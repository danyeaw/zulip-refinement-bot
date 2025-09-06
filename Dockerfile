# Multi-stage build for production-ready container
FROM condaforge/mambaforge:latest as builder

# Set working directory
WORKDIR /app

# Copy environment file
COPY environment.yml .

# Create conda environment
RUN mamba env create -f environment.yml && \
    mamba clean -afy

# Production stage
FROM condaforge/mambaforge:latest

# Set labels for better container management
LABEL maintainer="your.email@example.com"
LABEL description="Zulip Refinement Bot - A modern bot for batch story point estimation"
LABEL version="1.0.0"

# Create non-root user for security
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Set working directory
WORKDIR /app

# Copy conda environment from builder
COPY --from=builder /opt/conda/envs/zulip-refinement-bot /opt/conda/envs/zulip-refinement-bot

# Make RUN commands use the new environment
SHELL ["conda", "run", "-n", "zulip-refinement-bot", "/bin/bash", "-c"]

# Copy application code
COPY src/ src/
COPY pyproject.toml .
COPY README.md .
COPY LICENSE .

# Install the application
RUN conda run -n zulip-refinement-bot pip install -e .

# Create data directory for SQLite database
RUN mkdir -p /app/data && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV LOG_FORMAT=json
ENV DATABASE_PATH=/app/data/refinement.db

# Expose health check endpoint (if implemented)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD conda run -n zulip-refinement-bot python -c "import sys; sys.exit(0)"

# Default command
CMD ["conda", "run", "--no-capture-output", "-n", "zulip-refinement-bot", "zulip-refinement-bot", "run", "--log-format", "json"]
