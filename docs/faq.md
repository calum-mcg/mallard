# Frequently Asked Questions

### What is hydration?
Hydration in Mallard refers to the process of copying the minimum required subset of data from your production BigQuery environment into your local DuckDB database. 

When you run a command like `mallard run --select my_model`, Mallard analyzes the Directed Acyclic Graph (DAG) to find all the root tables (`declarations` in Dataform) that `my_model` depends on. Rather than downloading entire massive tables (which could be petabytes of data), Mallard:
1. Applies any `partition_filters` defined in your `.mallard.yml`.
2. Appends a strict `LIMIT` clause (defaulting to 1000 rows).
3. Executes this lightweight query against BigQuery and downloads the result to your machine via PyArrow.
4. Loads those rows into a local DuckDB table stored inside `.mallard/cache.duckdb`.

Once hydration is complete, all subsequent Dataform SQL execution happens locally in DuckDB at lightning speed without querying BigQuery again (unless you explicitly request a cache refresh).

### How do I clear the local cache?
If your local DuckDB database (`.mallard/cache.duckdb`) gets corrupted or you want to free up space, simply run `mallard clean` from the root of your Dataform project. This deletes the `.mallard/` directory entirely. The next time you run a model, Mallard will automatically recreate the database and re-hydrate required sources.

### Does Mallard modify my Dataform code?
No! Mallard reads your existing Dataform SQLX files, compiles them, and transpiles the generated SQL dynamically in memory before passing it to DuckDB. Your actual files are never modified, and they remain 100% compatible with Google Cloud Dataform execution.
