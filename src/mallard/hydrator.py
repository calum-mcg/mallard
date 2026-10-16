import datetime
import os
from pathlib import Path

import duckdb
import sqlglot
import yaml
from google.cloud import bigquery
from rich.console import Console
from rich.prompt import Confirm

console = Console()


def _get_partition_field(bq_client, table_ref, depth=0):
    """
    Recursively fetch table metadata to find the partition field.
    If it's a view, parse the SQL to find underlying tables and check them.
    """
    if depth > 5:  # Prevent infinite recursion
        return None

    try:
        table = bq_client.get_table(table_ref)

        if table.table_type == "TABLE" and table.time_partitioning:
            if table.time_partitioning.field:
                return table.time_partitioning.field
            return "_PARTITIONDATE"

        elif table.table_type == "VIEW" and table.view_query:
            try:
                parsed = sqlglot.parse_one(table.view_query, read="bigquery")
                for t in parsed.find_all(sqlglot.exp.Table):
                    sub_table_ref = t.sql(dialect="bigquery").replace("`", "")
                    part_col = _get_partition_field(bq_client, sub_table_ref, depth + 1)
                    if part_col:
                        return part_col
            except Exception:
                pass

    except Exception:
        pass

    return None


def get_config():
    config_path = Path(".mallard.yml")
    if not config_path.exists():
        console.print(
            "[bold yellow].mallard.yml not found. Launching setup wizard...[/bold yellow]"
        )
        from mallard.init_wizard import run_init_wizard

        run_init_wizard()

        # Check again to ensure the user didn't cancel the wizard
        if not config_path.exists():
            console.print(
                "[bold red]Initialization cancelled or failed. Aborting.[/bold red]"
            )
            import sys

            sys.exit(1)

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def hydrate_sources(dag, selected_nodes, compiled_graph=None):
    """
    Identifies required upstream source declarations for the target graph subset.
    Pulls partition subsets from BigQuery into .mallard/cache.duckdb via Arrow/Parquet.
    """
    config = get_config()
    row_limit = config.get("row_limit", 1000)
    partition_filters = config.get("partition_filters", {})

    # Extract vars from compiled graph
    df_vars = {}
    if compiled_graph:
        df_vars = compiled_graph.get("projectConfig", {}).get("vars", {})

    # Identify required sources (declarations that are ancestors of selected_nodes)
    required_sources = set()
    for node in selected_nodes:
        ancestors = dag.predecessors(node)
        for anc in ancestors:
            if anc not in selected_nodes:
                required_sources.add(anc)

    if not required_sources:
        console.print(
            "[yellow]No upstream BigQuery sources required for the selected models.[/yellow]"
        )
        return

    # Ensure .mallard dir exists
    os.makedirs(".mallard", exist_ok=True)
    db_path = ".mallard/cache.duckdb"

    bq_client = bigquery.Client()
    con = duckdb.connect(db_path)

    # Set memory limit and temp directory for large hydrations
    con.execute("PRAGMA memory_limit='8GB'")
    os.makedirs(".mallard/tmp", exist_ok=True)
    con.execute("PRAGMA temp_directory='.mallard/tmp'")
    con.execute("PRAGMA max_temp_directory_size='55GiB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET threads=1")

    # Load BigQuery extension
    con.execute("SET enable_progress_bar=true")
    con.execute("SET enable_progress_bar_print=true")
    con.execute("INSTALL bigquery FROM community")
    con.execute("LOAD bigquery")

    # Initialize metadata table
    con.execute("""
        CREATE TABLE IF NOT EXISTS _mallard_metadata (
            source_id VARCHAR,
            partition_filter VARCHAR,
            fetched_at TIMESTAMP
        )
    """)

    sources_to_fetch = []

    for source_id in required_sources:
        node_data = dag.nodes[source_id]
        target = node_data.get("target", {})
        database = target.get("database")
        schema = target.get("schema")
        name = target.get("name")

        table_name = f"{schema}_{name}"

        bq_table_ref = f"{database}.{schema}.{name}" if database else f"{schema}.{name}"

        # Determine formatted filter
        formatted_filter = ""
        if name in partition_filters:
            filter_str = partition_filters[name]
            try:
                formatted_filter = filter_str.format(**df_vars)
            except KeyError:
                pass
        elif table_name in partition_filters:
            filter_str = partition_filters[table_name]
            try:
                formatted_filter = filter_str.format(**df_vars)
            except KeyError:
                pass
        elif source_id in partition_filters:
            filter_str = partition_filters[source_id]
            try:
                formatted_filter = filter_str.format(**df_vars)
            except KeyError:
                pass

        # Infer partition filter if not explicitly provided
        if not formatted_filter and "date_id" in df_vars:
            part_col = _get_partition_field(bq_client, bq_table_ref)
            if part_col:
                formatted_filter = f"{part_col} = '{df_vars['date_id']}'"

        # Check if this exact partition filter was already fetched
        cached_record = con.execute(
            "SELECT fetched_at FROM _mallard_metadata WHERE source_id = ? AND partition_filter = ?",
            (source_id, formatted_filter),
        ).fetchone()

        if cached_record:
            fetched_at = cached_record[0]
            # Simple human readable time difference
            diff = datetime.datetime.now() - fetched_at  # noqa: DTZ005
            hours, remainder = divmod(diff.total_seconds(), 3600)
            minutes, _ = divmod(remainder, 60)
            time_ago = (
                f"{int(hours)}h {int(minutes)}m ago"
                if hours > 0
                else f"{int(minutes)}m ago"
            )
            console.print(f"✅ [dim]{source_id} (cached {time_ago})[/dim]")
            continue

        # If not cached, we need to fetch it
        sources_to_fetch.append(
            {
                "source_id": source_id,
                "database": database,
                "schema": schema,
                "name": name,
                "table_name": table_name,
                "formatted_filter": formatted_filter,
            }
        )

    if not sources_to_fetch:
        con.close()
        return

    # Calculate estimated costs via dry run
    total_bytes_processed = 0
    for source in sources_to_fetch:
        database = source["database"]
        schema = source["schema"]
        name = source["name"]
        formatted_filter = source["formatted_filter"]

        bq_table_ref = f"{database}.{schema}.{name}" if database else f"{schema}.{name}"
        query = f"SELECT * FROM `{bq_table_ref}`"
        if formatted_filter:
            query += f" WHERE {formatted_filter}"
        if row_limit > 0:
            query += f" LIMIT {row_limit}"

        try:
            job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
            dry_run_job = bq_client.query(query, job_config=job_config)
            total_bytes_processed += dry_run_job.total_bytes_processed or 0
        except Exception:
            pass  # Ignore dry run errors (e.g. UDFs)

    total_mb = total_bytes_processed / (1024 * 1024)
    total_cost = (total_bytes_processed / (1024**4)) * 6.25

    # Prompt user
    source_names = [s["source_id"] for s in sources_to_fetch]
    prompt_msg = f"[bold yellow]The following sources need to be hydrated from BigQuery: {', '.join(source_names)}.\n"
    prompt_msg += f"This will process ~{total_mb:.2f} MB and cost ~${total_cost:.4f}. Proceed?[/bold yellow]"

    if not Confirm.ask(prompt_msg):
        console.print("[bold red]Hydration cancelled.[/bold red]")
        con.close()
        import sys

        sys.exit(1)

    for source in sources_to_fetch:
        source_id = source["source_id"]
        database = source["database"]
        schema = source["schema"]
        name = source["name"]
        table_name = source["table_name"]
        formatted_filter = source["formatted_filter"]

        filter_msg = f"filter: {formatted_filter}" if formatted_filter else "no filter"
        limit_msg = f"limit: {row_limit}" if row_limit > 0 else "no limit"
        console.print(
            f"⏳ [dim]Hydrating {source_id} ({filter_msg}, {limit_msg})...[/dim]"
        )

        bq_table_ref = f"{database}.{schema}.{name}" if database else f"{schema}.{name}"
        query = f"SELECT * FROM `{bq_table_ref}`"

        if formatted_filter:
            query += f" WHERE {formatted_filter}"

        if row_limit > 0:
            query += f" LIMIT {row_limit}"

        try:
            # Execute dry run in BigQuery to get exact cost metrics
            job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
            dry_run_job = bq_client.query(query, job_config=job_config)

            bytes_billed = dry_run_job.total_bytes_processed or 0
            mb_processed = bytes_billed / (1024 * 1024)
            cost = (bytes_billed / (1024**4)) * 6.25

            # Check if table exists
            table_exists = (
                con.execute(
                    f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{table_name}'"
                ).fetchone()[0]
                > 0
            )

            if table_exists:
                if formatted_filter:
                    # Delete existing partition data to overwrite
                    con.execute(f"DELETE FROM {table_name} WHERE {formatted_filter}")
                else:
                    # No filter, overwrite whole table
                    con.execute(f"DROP TABLE {table_name}")
                    table_exists = False

            # Use DuckDB's native bigquery extension to fetch data directly
            # We escape single quotes in the query string
            safe_query = query.replace("'", "''")
            bq_project = bq_client.project

            if not table_exists:
                con.execute(
                    f"CREATE TABLE {table_name} AS SELECT * FROM bigquery_query('{bq_project}', '{safe_query}')"
                )
            else:
                con.execute(
                    f"INSERT INTO {table_name} SELECT * FROM bigquery_query('{bq_project}', '{safe_query}')"
                )

            # Get the exact row count fetched
            if formatted_filter:
                total_rows = con.execute(
                    f"SELECT COUNT(*) FROM {table_name} WHERE {formatted_filter}"
                ).fetchone()[0]
            else:
                total_rows = con.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()[0]

            # Update metadata
            con.execute(
                "DELETE FROM _mallard_metadata WHERE source_id = ? AND partition_filter = ?",
                (source_id, formatted_filter),
            )
            con.execute(
                "INSERT INTO _mallard_metadata VALUES (?, ?, CURRENT_TIMESTAMP)",
                (source_id, formatted_filter),
            )

            console.print(
                f"✅ [green]{source_id}[/green] [dim](Fetched {total_rows:,} rows, {mb_processed:.2f} MB processed, ~${cost:.4f})[/dim]"
            )

            if total_rows == 0:
                console.print(
                    f"[bold yellow]Warning: 0 rows returned for {source_id}. Check your partition filters and date_id.[/bold yellow]"
                )

        except Exception as e:
            error_str = str(e)
            if (
                "Cannot query over table" in error_str
                and "without a filter over column(s)" in error_str
            ):
                console.print(
                    f"[bold red]Failed to hydrate {source_id}: The underlying table requires a partition filter.[/bold red]"
                )
                console.print(
                    f"[yellow]Please add a partition filter for '{source_id}' or '{name}' in your .mallard.yml file.[/yellow]"
                )
            elif (
                "404 Not found" in error_str
                or "notFound" in error_str
                or "Not found: Table" in error_str
            ):
                # console.print(f"[yellow]Table not found for {source_id}, checking if it's a UDF...[/yellow]")
                try:
                    routine_query = (
                        f"SELECT ddl FROM `{database}.{schema}.INFORMATION_SCHEMA.ROUTINES` WHERE routine_name = '{name}'"
                        if database
                        else f"SELECT ddl FROM `{schema}.INFORMATION_SCHEMA.ROUTINES` WHERE routine_name = '{name}'"
                    )
                    res = list(bq_client.query(routine_query))
                    if res and res[0][0]:
                        ddl = res[0][0]
                        from mallard.transpiler import transpile_to_duckdb

                        duckdb_sql = transpile_to_duckdb(ddl)
                        try:
                            con.execute(duckdb_sql)
                            console.print(f"✅ [green]{source_id} (UDF)[/green]")
                            con.execute(
                                "DELETE FROM _mallard_metadata WHERE source_id = ? AND partition_filter = ?",
                                (source_id, ""),
                            )
                            con.execute(
                                "INSERT INTO _mallard_metadata VALUES (?, ?, CURRENT_TIMESTAMP)",
                                (source_id, ""),
                            )
                        except duckdb.CatalogException as ex:
                            if "already exists" in str(ex):
                                console.print(f"✅ [dim]{source_id} (UDF cached)[/dim]")
                                con.execute(
                                    "DELETE FROM _mallard_metadata WHERE source_id = ? AND partition_filter = ?",
                                    (source_id, ""),
                                )
                                con.execute(
                                    "INSERT INTO _mallard_metadata VALUES (?, ?, CURRENT_TIMESTAMP)",
                                    (source_id, ""),
                                )
                            else:
                                raise
                    else:
                        console.print(
                            f"[bold red]Failed to hydrate {source_id}: Not found as Table or UDF.[/bold red]"
                        )
                except Exception as ex:
                    console.print(
                        f"[bold red]Failed to hydrate {source_id} as UDF: {ex!s}[/bold red]"
                    )
            else:
                console.print(
                    f"[bold red]Failed to hydrate {source_id}: {e!s}[/bold red]"
                )

    con.close()
