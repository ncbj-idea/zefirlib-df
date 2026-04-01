# Dockerfile for DataFusion Core Application
# Lightweight container without Airflow dependencies

ARG PYTHON_IMAGE=python:3.12-slim

# Proxy configuration (set via --build-arg or docker-compose args)
ARG http_proxy
ARG https_proxy
ARG no_proxy

# User configuration (set via docker-compose to match host user)
ARG HOST_UID=1000
ARG HOST_GID=1000

# ===========================================
# Stage 1: Builder - Install dependencies and project
# ===========================================
FROM ${PYTHON_IMAGE} AS builder

# Install uv
RUN pip install --no-cache-dir uv

# UV specific environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/root/.cache/uv

WORKDIR /app

# Layer 1: Install dependencies only (cached)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=${UV_CACHE_DIR} \
    uv sync --locked --no-install-project --no-editable

# Layer 2: Copy project and sync
COPY datafusion/ ./datafusion/
RUN --mount=type=cache,target=${UV_CACHE_DIR} \
    uv sync --locked --no-editable

# ===========================================
# Stage 2: Core Runtime (CLI only)
# ===========================================

FROM ${PYTHON_IMAGE} AS core

# User configuration (must be re-declared in each stage)
ARG HOST_UID=1000
ARG HOST_GID=1000

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROJECT_DIR=/app

WORKDIR ${PROJECT_DIR}

# Install runtime dependencies (CLI only - no GUI)
RUN --mount=type=cache,target=/var/cache/apt/archives \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder (no source code)
COPY --from=builder /app/.venv /app/.venv

# Activate virtual environment via PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy additional files needed for runtime
COPY alembic.ini ${PROJECT_DIR}/
COPY logging.yml ${PROJECT_DIR}/
COPY configs/ ${PROJECT_DIR}/configs/
COPY datafusion/alembic/ ${PROJECT_DIR}/datafusion/alembic/
COPY datafusion/resources/ ${PROJECT_DIR}/datafusion/resources/
COPY datafusion/sql_queries/ ${PROJECT_DIR}/datafusion/sql_queries/
COPY scripts/ ${PROJECT_DIR}/scripts/
COPY datafusion/gui/ ${PROJECT_DIR}/datafusion/gui/

RUN chmod +x ${PROJECT_DIR}/scripts/db-migrate.sh

# Create non-root user matching host UID/GID for proper file permissions
RUN groupadd --gid $HOST_GID appgroup && \
    useradd --uid $HOST_UID --gid $HOST_GID --shell /bin/bash --create-home appuser && \
    chown -R $HOST_UID:$HOST_GID /app

# Switch to non-root user
USER $HOST_UID

# Default command - show help
CMD ["run", "--help"]

# ===========================================
# Stage 3: GUI Runtime (optional)
# ===========================================
FROM core AS gui

# Install GUI dependencies on top of core
RUN --mount=type=cache,target=/var/cache/apt/archives \
    --mount=type=cache,target=/var/lib/apt/lists \
    apt-get update && apt-get install -y --no-install-recommends \
    # X11 client libraries
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxrandr2 \
    libxfixes3 \
    libxi6 \
    # Qt platform/xcb plugin dependencies
    libxcb1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    # OpenGL (required by Qt)
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libdbus-1-3 \
    libsm6 \
    libice6 \
    # Font rendering
    libfontconfig1 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Use xcb platform plugin (X11-compatible, works over forwarding)
ENV QT_QPA_PLATFORM=xcb
# Disable Qt's crash handler (not needed in container)
ENV QT_LOGGING_RULES="*.debug=false"

# Override CMD to show GUI hint
CMD ["gui", "--help"]
