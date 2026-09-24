<div align="center">
  <img src="assets/mallard-logo.png" alt="Mallard Logo" width="200"/>
  <h1>Mallard</h1>
  <p><strong>A fast local execution engine for Dataform projects.</strong></p>

  [![Python](https://img.shields.io/badge/Python-3.14%2B-blue.svg)](https://python.org)
  [![DuckDB](https://img.shields.io/badge/DuckDB-1.1%2B-yellow.svg)](https://duckdb.org/)
  [![Dataform](https://img.shields.io/badge/Dataform-CLI-green.svg)](https://cloud.google.com/dataform)
  [![License](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
</div>

---

Mallard eliminates BigQuery slot costs during local development by compiling Dataform DAGs, transpiling BigQuery SQL dialect to DuckDB, and maintaining a local `.mallard/` database cache.

### Documentation

**Read the full documentation at [https://calum-mcg.github.io/mallard/](https://calum-mcg.github.io/mallard/)**

### Quick Start Guide

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

Navigate to your actual Dataform project directory and run Mallard just like a standard user would:
```bash
cd /path/to/your/dataform-project

# Initialize the local config
mallard init

# Run your models
mallard run --select +my_model+
```

### Local Development & Testing

If you are developing Mallard and want to run tests locally:

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
