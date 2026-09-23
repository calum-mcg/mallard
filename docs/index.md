# Mallard

Mallard eliminates BigQuery slot costs during local development by compiling Dataform DAGs, transpiling BigQuery SQL dialect to DuckDB, and maintaining a local `.mallard/` database cache.

## How it works

When you run a command like `mallard run --select my_model`, Mallard performs the following steps:

1. **Compiles Dataform**: It uses the underlying `@dataform/cli` to parse your `workflow_settings.yaml` and `.sqlx` definitions into a JSON compiled graph.
2. **Builds the DAG**: Resolves model dependencies and evaluates selection criteria (e.g. tags, specific models, upstream/downstream flags).
3. **Hydrates Sources**: Detects which base source `declarations` are required for the selected subset of models. It then executes limited `SELECT * FROM source LIMIT N` queries directly against BigQuery, downloads the result using PyArrow, and caches it locally in DuckDB.
4. **Transpiles SQL**: Automatically translates BigQuery specific SQL dialects (like `FARM_FINGERPRINT()`, `UNNEST(array) WITH OFFSET`, `EXTRACT(DATE FROM ts)`, string aggregation, and structural types) into their DuckDB equivalents using `sqlglot`.
5. **Executes Locally**: Runs the translated SQL directly inside the fast local DuckDB `.mallard/cache.duckdb` cache. Incremental merge strategies, full refreshes, and custom pre/post operations are handled seamlessly.
6. **Validates Assertions**: If any assertions are selected, it transpiles and runs them locally. If any rows are returned by an assertion, the execution stops and an error is logged.

## Prerequisites

Before running Mallard, you need:

1. **Google Cloud Auth**: You must be authenticated with Google Cloud using Application Default Credentials (ADC). Mallard uses the `google-cloud-bigquery` library to hydrate your local DuckDB cache from BigQuery.
   ```bash
   gcloud auth application-default login
   ```
2. **Dataform CLI**: You must be working inside a valid Dataform project (e.g., a folder containing `workflow_settings.yaml`). The Dataform core version specified in your project will be used.
