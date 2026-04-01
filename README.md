# DataFusion

DataFusion is a Python-based data integration platform designed to gather, combine, and analyze Polish geospatial and complementary datasets. Its primary goal is to create a unified and comprehensive view of building data, heating sources, and solar potential to support climate data analysis and energy transition planning.

The full documentation for the project, including how to prepare input data, configure the pipeline, and interpret results, can be found at:
[zefir.ncbj.gov.pl](https://zefir.ncbj.gov.pl/dokumentacja)

## ❗️ Required steps

1. Copy the environment template:
```bash
cp template.env .env
```
On NCBJ ifnrastructure uncomment the configuration lines in `.env` as instructed.

2. Set TERC code in `/configs/global.yml`
3. Check `/configs/data_sources/ceeb.yml`, and place your CEEB data files inside ./input folder.

## Quick Start with Docker 🐋

### Prerequisites

- Docker installed and running

- Launch docker desktop or check if docker is available:
```bash
docker ps
```

### Start the application:

- Option 1: Using Make (Linux/Mac/WSL)

```bash
make docker-start
# or
make docker-gui
# for GUI interface
```

- Option 2: Using Docker directly (Windows without WSL)

If you're running on Windows without WSL, use `docker compose` directly:

```powershell
# Start database
docker compose up -d db

# Start core services (in a new terminal, keep db running)
docker compose up core

# Or start GUI (instead of core)
docker compose up gui
```

#### Available Docker Commands

| Command (Run in project root) | Description |
|-------------------------------|-------------|
| `docker compose up -d db` | Start database only |
| `docker compose up core` | Start database + core app |
| `docker compose up gui` | Start database + GUI interface |
| `docker compose down` | Stop all services |
| `docker compose ps` | Show container status |
| `docker compose logs -f` | Follow container logs |
| `docker compose run --rm core <command>` | Run a specific command |

#### Run CLI commands inside container:

```powershell
# Import data sources
docker compose run --rm core bdot
docker compose run --rm core borders
docker compose run --rm core kiut
docker compose run --rm core ceeb
docker compose run --rm core prg
docker compose run --rm core pvgis

# Generate reports
docker compose run --rm core report

# Merge data
docker compose run --rm core merge

# Run full pipeline
docker compose run --rm core all_runner --terc 123456
```

> **Note:** Running commands out of order may cause errors due to dependencies.

### Functional testing with mock data
1. You need a CEEB files. For testing app you can use mock data from

```
tests/resources/data_analyzer/ceeb_classes.xlsx
tests/resources/data_analyzer/ceeb_devices.xlsx
```
2. You will need result of manual inventory check. You can use script to generate them
```
datafusion/postprocessing/generate_mock_inwentaryzacja.py
uv run datafusion/postprocessing/generate_mock_inwentaryzacja.py output/terc_number/inventory_files/my-mock-inventory.xlsx
```


---

## Local Development Setup

### Prerequisites
- ℹ️ Use unix system, if windows use WSL.
- Python 3.12+
- GDAL (for geospatial processing)
- Docker (for database)
- PostgreSQL 13+ with PostGIS 3+ if not using Docker

### Installation

```bash
# Install dependencies
make install

# For development install development dependencies and pre-commit hooks
make install-dev
```

### Configuration

1. Copy the environment template:
```bash
cp template.env .env
```

2. Configure your `.env` file with database and logging settings:
```env
POSTGRES_PORT=5432
POSTGRES_HOST=localhost
POSTGRES_DB="postgres"
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="postgres"
POSTGRES_DB_AIRFLOW=airflow
LOG_CFG=logging.yml
```

3. Setup database:
```bash
make build-database
```

4. Configure the modular configuration files in the `configs/` directory:
   - Edit `configs/global.yml` to set your TERC code
   - Configure data source settings in `configs/data_sources/`
   - Adjust processing parameters in `configs/processing/`
   - Modify postprocessing settings in `configs/postprocessing/`

See [configs/README.md](configs/README.md) for detailed configuration documentation.

### CLI Commands

Run from your local environment:

| Command | Description | Source |
|---------|-------------|--------|
| `bdot` | Topographic Objects Database | [Geoportal](https://www.geoportal.gov.pl/en/data/topographic-objects-database-bdot10k/) |
| `borders` | Administrative Boundaries | [Geoportal](https://www.geoportal.gov.pl/en/data/national-register-of-boundaries/) |
| `kiut` | Utilities Network (heating, gas) | [Geoportal](https://www.geoportal.gov.pl/en/data/utilities-network-gesut/) |
| `ceeb` | Heating devices data | [GUNB](https://www.gunb.gov.pl/podmenu/1713) |
| `prg` | National Register of Boundaries | [Geoportal](https://www.geoportal.gov.pl/en/data/national-register-of-boundaries/) |
| `pvgis` | Solar potential data | [PVGIS](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/) |
| `pvgis_merger` | Merge address with PVGIS data | - |
| `report` | Generate Excel report | - |
| `merge` | Merge CEEB with BDOT data | - |
| `gui` | Launch DataFusion GUI | - |
| `run` | Run full pipeline | - |

> **Note:** Running commands out of order may cause errors due to dependencies.

### Graphical User Interface (GUI)

The GUI lets you run the full DataFusion pipeline without the CLI and monitor logs in a single window.

#### Launch and use

Start the GUI:

```bash
start
```

Step-by-step usage:

1. Enter or confirm the TERC code (pre-filled from config if present).
2. Select the CEEB files: Devices and Classes (`.csv`, `.xlsx`, `.xls`).
3. (Optional) Enable report export to generate `buildings_report.xls`.
4. Click "Uruchom" to run the full process and watch logs in the terminal panel. If the TERC code or inventory folder is missing, the GUI shows an error message.
5. To run postprocessing script, choose the inventory folder and click "Uruchom z inwentaryzacja".

 

TERC codes can be found on the official  [eTeryt](https://eteryt.stat.gov.pl/eTeryt/rejestr_teryt/udostepnianie_danych/baza_teryt/uzytkownicy_indywidualni/wyszukiwanie/wyszukiwanie.aspx?contrast=default).

#### How it works

- The GUI loads YAML configuration and pre-fills fields.
- It validates inputs and persists updates to configuration files.
- It runs the selected module in the background and streams logs to the terminal panel.
- GUI styles live in [datafusion/gui/style.qss](datafusion/gui/style.qss).

### Configuration

The configuration system uses a modular structure with a global `terc` code that is automatically injected into all sub-configurations.

For detailed configuration documentation, see [configs/README.md](configs/README.md).

**Key configuration files:**

- `configs/config.yml` - Main entry point that imports all sub-configurations
- `configs/global.yml` - Global settings (TERC code)
- `configs/data_sources/` - Data source configurations (BDOT, Borders, KIUT, CEEB, Address, PVGIS)
- `configs/processing/` - Processing and merge configurations
- `configs/postprocessing/` - Postprocessing configurations (thresholds, sampling, estimation)

---


### Available Make Targets

| Target | Description |
|--------|-------------|
| `make help` | Show available targets |
| `make check-tools` | Verify GDAL tools (ogr2ogr, gdalinfo) are available |
| `make install` | Create venv and install main dependencies |
| `make install-dev` | Install dev dependencies and pre-commit hooks |
| `make lint` | Run ruff formatter and linter |
| `make test` | Run tests with coverage |
| `make clean` | Remove temporary files and venv |
| `make build-airflow` | Build and start Airflow services |
| `make build-database` | Build database and run migrations |
| `make docs` | Build Sphinx documentation |

### Database Migrations

1. Make changes to models in `datafusion/database/models/`
2. Ensure your `.env` is loaded:
```bash
export $(cat .env | xargs)
```
3. Create a new migration:
```bash
alembic revision --autogenerate -m "Brief description"
```
4. Apply migrations:
```bash
alembic upgrade head
```

### Building Documentation

```bash
make docs
```

Documentation will be available at `docs/build/index.html`.

### Project Structure

```
datafusion/
├── runners/           # CLI entry points
├── readers/           # Data extraction logic
├── database/          # SQLAlchemy models and sessions
├── configs/           # Pydantic configuration schemas
├── utils/             # Helper functions
├── alembic/           # Database migrations
├── reporting/         # Excel report generation
├── kiut/              # Utilities network processing
├── pvgis/             # Solar potential data processing
├── postprocessing/    # Data post-processing
└── ceeb_bdot_merger/  # CEEB and BDOT merging

configs/               # Modular configuration files
├── config.yml         # Main configuration entry point
├── global.yml         # Global settings (TERC code)
├── data_sources/      # Data source configurations
├── processing/        # Processing and merge configurations
└── postprocessing/    # Postprocessing configurations
```

### Running Tests

```bash
make test
```

### Code Style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
make lint
```

---

## License

IDEA NCBJ
