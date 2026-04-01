SHELL := /bin/bash

# Configuration
PYTHON := python3
VENV_DIR := .venv
VENV_ACTIVATE := $(VENV_DIR)/bin/activate
PYPROJECT := pyproject.toml
PRE_COMMIT := .pre-commit-config.yaml
DOCS_DIR := docs
DOCS_SOURCE := $(DOCS_DIR)/source
DOCS_BUILD := $(DOCS_DIR)/build

# System dependencies
OGR2OGR := ogr2ogr
GDALINFO := gdalinfo

# Check for required system tools
check-tools:
	@echo "Checking for required system tools..."
	@if ! command -v $(OGR2OGR) && ! command -v $(GDALINFO); then \
		echo "Error: ogr2ogr and gdalinfo are required but not found in PATH"; \
		echo "Please install GDAL (https://gdal.org/) and ensure ogr2ogr is available"; \
		exit 1; \
	fi
	@echo "Required tools found: ogr2ogr, gdalinfo"

# Check for uv
UV := $(shell command -v uv 2>/dev/null)

create-venv:
	@if [ ! -d "$(VENV_DIR)" ] && [! -z "$(UV)" ]; then \
		$(PYTHON) -m venv $(VENV_DIR); \
		@echo "Virtual environment created."; \
	fi

# Editable install flag
EDITABLE ?= yes

# Venv creation and sync commands based on available tool
ifeq ($(UV),)
	# Fallback to pip if uv is not available
	VENV_CREATE := $(PYTHON) -m venv $(VENV_DIR)
	PIP_INSTALL := pip install "."
	PIP_INSTALL_DEV := pip install ".[dev]"
	DOCS_INSTALL := pip install ".[docs]"
	ifeq ($(EDITABLE), yes)
		PIP_INSTALL := pip install -e "."
		PIP_INSTALL_DEV := pip install -e ".[dev]"
		DOCS_INSTALL := pip install -e ".[docs]"		
	endif
else
	# Use uv for venv creation and sync
	PIP_INSTALL := uv sync
	PIP_INSTALL_DEV := uv sync --all-extras
	DOCS_INSTALL := uv sync --extra docs
endif


# Phony targets
.PHONY: help check-tools install install-dev lint clean docker-gui build-airflow build-database docs test docker-start docker-run

# Default target
.DEFAULT_GOAL := help

# Help target
help:
	@echo "Available targets:"
	@echo "  help          - Show this help message"
	@echo "  check-tools   - Verify required system tools are available"
	@echo "  install       - Create venv and install dependencies"
	@echo "  install-dev   - Install dev dependencies and pre-commit hooks"
	@echo "  lint          - Run code formatting and linting"
	@echo "  clean         - Remove temporary files and venv"
	@echo ""
	@echo "Docker targets:"
	@echo "  docker-start   - Start core services (database + app)"
	@echo "  docker-gui     - Start GUI service"
	@echo "  docker-run     - Run core container interactively"
	@echo "  build-airflow  - Build and start all services including Airflow"
	@echo ""
	@echo "Other targets:"
	@echo "  docs          - Build documentation"
	@echo "  test          - Run tests"
	@echo ""
	@echo "Examples:"
	@echo "  make docker-start                    # Start services"
	@echo "  make docker-run ARGS=\"bdot\"        # Run bdot command"
	@echo ""
	@if [ -z "$(UV)" ]; then \
		echo "uv not found - using pip for installations"; \
	else \
		echo "uv found at $(UV) - using uv for faster installations"; \
	fi


# Install targets
install: check-tools create-venv $(VENV_ACTIVATE)
	@echo "Installing dependencies..."
	$(PIP_INSTALL)
	@echo "Dependencies installed successfully."

install-dev: check-tools create-venv $(VENV_ACTIVATE)
	@echo "Installing development dependencies..."
	$(PIP_INSTALL_DEV)
	@echo "Installing pre-commit hooks..."
	pre-commit install
	@echo "Development environment ready."


# Linting
lint:
	@echo "Running ruff formatter and linter..."
	. $(VENV_ACTIVATE) && ruff check .
	. $(VENV_ACTIVATE) && ruff format --check .
	@echo "Linting completed."

# Testing
test:
	@echo "Running tests..."
	. $(VENV_ACTIVATE) && pytest -v --cov=datafusion --cov-report=term-missing
	@echo "Tests completed."

# Cleanup
clean:
	@echo "Cleaning up..."
	@rm -rf $(VENV_DIR) .mypy_cache .pytest_cache .tox __pycache__
	@find . -type d -name __pycache__ -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.pyd" -delete
	@echo "Cleanup completed."

# Docker - GUI service
docker-gui:
	@git update-index --chmod=+x scripts/run-gui-docker.sh
	@echo "Starting GUI service..."
	@bash scripts/run-gui-docker.sh
	@echo "GUI service started."

# Docker - Airflow services (optional profile)
build-airflow:
	@echo "Building all services including Airflow..."
	@docker compose --profile airflow build
	@docker compose --profile airflow up -d
	@echo "All services started. Airflow UI available at http://localhost:8080"

# Get current user UID and GID for Docker
HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

# Docker - Start core services
docker-start:
	@echo "Starting core services (database + app)..."
	@mkdir -p input output
	@HOST_UID=$(HOST_UID) HOST_GID=$(HOST_GID) docker compose up core
	@echo "Services started. Run 'docker compose logs -f' to view logs."

# Docker - Run core container with arguments
docker-run:
	@echo "Running core container with args: $(ARGS)..."
	@HOST_UID=$(HOST_UID) HOST_GID=$(HOST_GID) docker compose run --rm core $(ARGS)

# Database - Local development
build-database: install
	@echo "Building database..."
	@docker compose down db -v
	@docker compose up -d db
	@echo "Waiting for database to be ready..."
	@sleep 4
	@echo "Running database migrations..."
	. $(VENV_ACTIVATE) && alembic upgrade head
	@echo "Database ready."

# Documentation
docs: $(VENV_ACTIVATE)
	@echo "Installing documentation dependencies..."
	. $(VENV_ACTIVATE) && $(DOCS_INSTALL)
	@echo "Generating API documentation..."
	@mkdir -p $(DOCS_SOURCE) $(DOCS_BUILD)
	sphinx-apidoc -o $(DOCS_SOURCE) .
	@echo "Building HTML documentation..."
	sphinx-build -b html $(DOCS_SOURCE) $(DOCS_BUILD)
	@echo "Documentation built successfully."
	@echo "Documentation available at: file://$(abspath $(DOCS_BUILD))/index.html"

