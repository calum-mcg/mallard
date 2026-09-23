# CLI Reference

Mallard provides a streamlined CLI built with `typer`. You can append `--help` to any command to see all available arguments.

```bash
mallard --help
```

### `init`
Launches the interactive CLI setup wizard to generate a `.mallard.yml` configuration file in your project root.

**Example:**
```bash
mallard init
```

### `fetch`
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

### `run`
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

### `iterate`
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

### `clean`
Purges the `.mallard/` database cache and temporary artifacts.

**Example:**
```bash
mallard clean
```
