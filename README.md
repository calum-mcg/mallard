<div align="center">
  <img src="assets/mallard-logo.png" alt="Mallard Logo" width="200"/>
  <h1>Mallard</h1>
  <p><strong>A fast local execution engine for Dataform projects.</strong></p>

  [![Python](https://img.shields.io/badge/Python-3.14%2B-blue.svg)](https://python.org)
  [![DuckDB](https://img.shields.io/badge/DuckDB-1.1%2B-yellow.svg)](https://duckdb.org/)
  [![Dataform](https://img.shields.io/badge/Dataform-CLI-green.svg)](https://cloud.google.com/dataform)
  [![License](https://img.shields.io/badge/License-MIT-blue.svg)](#)
</div>

---

Mallard eliminates BigQuery slot costs during local development by compiling Dataform DAGs, transpiling BigQuery SQL dialect to DuckDB, and maintaining a local `.mallard/` database cache.

## 🚀 Quick Start Guide

Install Mallard globally using `uv`:

```bash
# Using uv tool (recommended)
uv tool install mallard

# Or using uv pip
uv pip install mallard
```

Before running Mallard, ensure you have authenticated with Google Cloud using Application Default Credentials (ADC), as Mallard uses the `google-cloud-bigquery` library to hydrate your local DuckDB cache:

```bash
gcloud auth application-default login
```

## 🛠️ Local Development

If you are developing Mallard or want to test it locally against your own Dataform project, you can install it in "editable" mode using `uv`. 

1. **Install Mallard globally in editable mode:**
   Navigate to your local `mallard` repository and run:
   ```bash
   uv tool install -e .
   ```
   *(Note: This makes the `mallard` command available globally on your machine. Because of the `-e` editable flag, any changes you make to the Mallard source code will instantly be reflected without needing to reinstall.)*

2. **Test it in your Dataform project:**
   Navigate to your actual Dataform project directory and run Mallard just like a standard user would:
   ```bash
   cd /path/to/your/dataform-project
   
   # Initialize the local config
   mallard init
   
   # Run your models
   mallard run --select +my_model+
   ```

## 🧪 Linting & Testing

Mallard uses `ruff` for fast linting and `pytest` for its test suite. Both are managed via `uv` in the development dependencies.

**To run the test suite:**
```bash
uv run pytest
```

**To run the linter:**
```bash
uv run ruff check
```

**To format your code automatically:**
```bash
uv run ruff format
```

## 💻 CLI Surface

Mallard provides a streamlined CLI built with `typer`. You can append `--help` to any command to see all available arguments.

```bash
mallard --help
```

### 1. `init`
Launches the interactive CLI setup wizard to generate a `.mallard.yml` configuration file in your project root.

**Example:**
```bash
mallard init
```

### 2. `fetch`
Pre-hydrates or updates root BigQuery source partitions into local DuckDB. This is automatically run by `run` and `iterate`, but can be invoked manually.

**Arguments:**
* `--vars <str>`: Inject variables into compilation, e.g. `date_id=2023-01-01`

**Examples:**
```bash
# Fetch all sources
mallard fetch

# Fetch sources passing a specific variable to the compiler
mallard fetch --vars="date_id=2023-01-01"
```

### 3. `run`
Compiles the Dataform project and executes the DAG locally on DuckDB.

**Arguments:**
* `--select <str>`: Run specific models, e.g. `stg_orders`
* `--tags <str>`: Run models matching specified tags, e.g. `core,hourly`
* `--upstream`: (Boolean) Include upstream dependencies for selected models
* `--downstream`: (Boolean) Include downstream dependents for selected models
* `--refresh-sources`: Invalidate local DuckDB cache and re-fetch BigQuery partitions
* `--full-refresh`: Force full rebuild of incremental models
* `--vars <str>`: Inject variables into compilation, e.g. `date_id=2023-01-01`

**Examples:**
```bash
# Run specific model and its upstream dependencies (using boolean flag)
mallard run --select stg_orders --upstream

# Run specific model and its dependencies (using Dataform + syntax)
mallard run --select +stg_orders+

# Run with tags and force a full refresh of incremental models
mallard run --tags core,hourly --full-refresh

# Full pipeline example: invalidate cache, inject variables, run a model and dependents
mallard run --select stg_orders --downstream --refresh-sources --vars="date_id=2023-01-01"
```

### 4. `iterate`
Runs sequential iterations of models by dynamically injecting different variable values on each loop.

**Arguments:**
* `--var <str>` **(Required)**: Variable name to iterate over, e.g. `date_id`
* `--values <str>` **(Required)**: Comma-separated values to iterate, e.g. `2023-01-01,2023-01-02`
* `--select <str>`: Run specific models, e.g. `stg_orders`
* `--tags <str>`: Run models matching specified tags, e.g. `core,hourly`
* `--upstream`: (Boolean) Include upstream dependencies for selected models
* `--downstream`: (Boolean) Include downstream dependents for selected models
* `--refresh-sources`: Invalidate local DuckDB cache and re-fetch BigQuery partitions before executing
* `--full-refresh`: Force full rebuild of incremental models

**Examples:**
```bash
# Run a specific model sequentially across three different dates
mallard iterate --var date_id --values 2023-01-01,2023-01-02,2023-01-03 --select +my_model+

# Full pipeline example for backfilling a tagged set of models
mallard iterate \
  --var date_id \
  --values 2023-01-01,2023-01-02 \
  --tags core \
  --refresh-sources \
  --full-refresh
```

### 5. `clean`
Purges the `.mallard/` database cache and temporary artifacts.

**Example:**
```bash
mallard clean
```

## 🎥 Terminal Demo

*(Placeholder for animated SVG/GIF showcasing the interactive `mallard init` workflow and colorized `rich` execution log)*

## ⚙️ Configuration Specification

The `.mallard.yml` file sits at the root of your Dataform project:

```yaml
# Your BigQuery Project ID where original data resides
project_id: your-gcp-project

# The default dataset to use
dataset: dataform_dev

# How many rows to fetch from BigQuery when hydrating sources
row_limit: 1000

# Specify how to filter specific sources during hydration. 
# You can use injected --vars syntax like '{date_id}' which will be formatted.
partition_filters:
  your_source_name: "date_col = '{date_id}'"
```

## 🧩 Dataform Compatibility Matrix

| Feature | Supported | Details / Translation |
|---------|-----------|-----------------------|
| **Tables/Views** | ✅ Yes | Transpiled directly to `CREATE TABLE AS` or `CREATE VIEW AS` in DuckDB. |
| **Incremental** | ✅ Yes | Supports `incrementalQuery`, `uniqueKey` merges via Delete/Insert, and `Pre/PostOps`. Use `--full-refresh` to rebuild. |
| **Assertions** | ✅ Yes | Executes query; if rows are returned, Mallard logs a styled `[ERROR]` box and aborts the pipeline. |
| **Operations** | ✅ Yes | Runs raw SQL; transpiled to DuckDB dialect. |
| **Dependencies** | ✅ Yes | Full DAG resolution using NetworkX (`+model`, `model+`, `--tags`). |
| **Macros (JS)** | ✅ Yes | Handled upstream natively by `@dataform/cli`. |

## 🏗️ Core Tech Stack

*   **Package Management**: `uv` for ultra-fast installs and execution.
*   **CLI Engine & Prompts**: `typer`, `rich`, and `questionary` for stylish interactive terminal UI.
*   **Compilation**: `@dataform/cli` invoked via Python subprocess.
*   **Transpilation**: `sqlglot` (BigQuery $\rightarrow$ DuckDB).
*   **Graph Traversal**: `networkx` for DAG selection and dependency evaluation.
