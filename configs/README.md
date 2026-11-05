# DataFusion Configuration

This directory contains the modular configuration files for the DataFusion system.

## Directory Structure

```
configs/
├── README.md                    # This file
├── config.yml                    # Main configuration file (entry point)
├── global.yml                    # Global settings (TERC code, etc.)
├── data_sources/
│   ├── bdot.yml                  # BDOT (Building Database) configuration
│   ├── borders.yml               # Administrative boundaries configuration
│   ├── kiut.yml                  # Utility networks configuration
│   ├── ceeb.yml                  # Heating devices configuration
│   ├── address.yml               # Address points configuration
│   ├── pvgis.yml                 # Solar data configuration
│   ├── report.yml                # Report output configuration
├── processing/
│   ├── merge_config.yml          # Main merge configuration
│   └── merge_params/
│       ├── ceeb_params.yml       # CEEB merge parameters
│       ├── bdot_params.yml       # BDOT merge parameters
│       └── joining_params.yml    # Joining parameters (heat source mappings)
└── postprocessing/
    ├── thresholds.yml            # Thresholds and settings
    ├── sampling.yml              # Sampling configuration
    ├── estimation.yml            # Estimation parameters
    └── protostrefy.yml           # Protostrefy configuration
```

## Usage

### Loading Configuration

The configuration can be loaded using the `Config` class:

```python
from pathlib import Path
from datafusion.configs.config import Config

# Load the configuration
config = Config.from_file(Path('configs/config.yml'))

# Access configuration values
terc = config.global_config.terc
bdot_layer = config.bdot.layer_name
```

## Configuration Files

### Main Configuration (`config.yml`)

The main configuration file imports all sub-configurations using the `!include` directive:

```yaml
global: !include global.yml
bdot: !include data_sources/bdot.yml
borders: !include data_sources/borders.yml
# ... etc
```

### Global Configuration (`global.yml`)

Contains global settings shared across all components:
- `terc`: TERC code for the territorial unit

### Data Source Configurations

Each data source has its own configuration file:

- **`bdot.yml`**: Building database settings (layer name, table names, geometry column)
- **`borders.yml`**: Administrative boundaries (WFS URL, layer name, timeout)
- **`kiut.yml`**: Utility networks (layers, WMS settings, polygonization)
- **`ceeb.yml`**: Heating devices (file paths, schema)
- **`address.yml`**: Address points (WFS URL, layer name, geometry column)
- **`pvgis.yml`**: Solar data (coordinates, power settings)
- **`report.yml`**: Report output path

### Processing Configurations

- **`merge_config.yml`**: Main merge configuration with H3 resolution, classification method, etc.
- **`merge_params/ceeb_params.yml`**: CEEB-specific merge parameters
- **`merge_params/bdot_params.yml`**: BDOT-specific merge parameters
- **`merge_params/joining_params.yml`**: Joining parameters including heat source mappings

### Postprocessing Configurations

- **`thresholds.yml`**: Thresholds, normalization, building kind mappings
- **`sampling.yml`**: Sampling configuration (stratification, filters, inventory assignment)
- **`estimation.yml`**: Estimation parameters and taxonomy
- **`protostrefy.yml`**: Protostrefy configuration (expected columns, EE intensity)

## YAML Include Directive

The configuration system uses a custom `!include` directive to import sub-configurations:

```yaml
# In merge_config.yml
ceeb_params: !include merge_params/ceeb_params.yml
bdot_params: !include merge_params/bdot_params.yml
joining_params: !include merge_params/joining_params.yml
```

The include paths are resolved relative to the file containing the `!include` directive, allowing for nested includes.

## Benefits of Modular Configuration

1. **Easier Navigation**: Find settings quickly in smaller, focused files
2. **Better Maintenance**: Changes to one component don't risk affecting others
3. **Team Collaboration**: Multiple developers can work on different configs
4. **Environment Management**: Easy to have dev/staging/prod configs
5. **Testing**: Individual config sections can be tested independently
6. **Documentation**: Each file can have its own README
7. **Reusability**: Configurations can be shared across municipalities

## TERC Code Injection

The global TERC code is automatically injected into all sub-configurations that require it:

- `bdot`
- `kiut`
- `ceeb`
- `address`
- `report`
- `merge_config`

This is handled automatically by the configuration loading code in `src/datafusion/configs/config.py`.
