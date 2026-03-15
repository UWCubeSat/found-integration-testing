FROM debian:bookworm-slim

# Set environment variables for non-interactive installation
ENV DEBIAN_FRONTEND=noninteractive

# Install ca-certificates and curl, then install uv (minimal base has no apt-get)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.local/bin:$PATH"

COPY install.sh /tmp/install.sh

RUN chmod +x /tmp/install.sh && /tmp/install.sh && \
    rm -f /tmp/install.sh
