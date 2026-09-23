import os
from pathlib import Path

import duckdb
import yaml
from google.cloud import bigquery
from rich.console import Console

console = Console()

def get_config():
    config_path = Path(".mallard.yml")
    if not config_path.exists():
        console.print("[bold red].mallard.yml not found. Run `mallard init` first.[/bold red]")
        raise FileNotFoundError(".mallard.yml not found")
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
        console.print("[yellow]No upstream BigQuery sources required for the selected models.[/yellow]")
        return

    # Ensure .mallard dir exists
    os.makedirs(".mallard", exist_ok=True)
    db_path = ".mallard/cache.duckdb"

    bq_client = bigquery.Client()
    con = duckdb.connect(db_path)

    for source_id in required_sources:
        node_data = dag.nodes[source_id]
        target = node_data.get("target", {})
        database = target.get("database")
        schema = target.get("schema")
        name = target.get("name")
        
        table_name = f"{schema}_{name}"
        
        # Check if already hydrated
        exists = con.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{table_name}'").fetchone()[0]
        if exists:
            console.print(f"✅ [dim]{source_id} (cached)[/dim]")
            continue

        pass # console.print(f"⏳ Hydrating {source_id} (limit: {row_limit})")
        
        bq_table_ref = f"{database}.{schema}.{name}" if database else f"{schema}.{name}"
        query = f"SELECT * FROM `{bq_table_ref}`"
        
        # Apply partition filter if exists
        if name in partition_filters:
            filter_str = partition_filters[name]
            try:
                # Format the filter string with the variables
                formatted_filter = filter_str.format(**df_vars)
                query += f" WHERE {formatted_filter}"
                pass # hide
            except KeyError as e:
                pass # hide
        elif table_name in partition_filters:
            filter_str = partition_filters[table_name]
            try:
                formatted_filter = filter_str.format(**df_vars)
                query += f" WHERE {formatted_filter}"
                pass # hide
            except KeyError as e:
                pass # hide
        elif source_id in partition_filters:
            filter_str = partition_filters[source_id]
            try:
                formatted_filter = filter_str.format(**df_vars)
                query += f" WHERE {formatted_filter}"
                pass # hide
            except KeyError as e:
                pass # hide
                
        query += f" LIMIT {row_limit}"
        
        try:
            # Execute in BigQuery and get Arrow Table
            query_job = bq_client.query(query)
            arrow_table = query_job.to_arrow()
            
            # Register in DuckDB and persist
            con.register("temp_arrow_table", arrow_table)
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM temp_arrow_table")
            con.unregister("temp_arrow_table")
            
            console.print(f"✅ [green]{source_id}[/green]")
        except Exception as e:
            if "404 Not found" in str(e) or "notFound" in str(e):
                # console.print(f"[yellow]Table not found for {source_id}, checking if it's a UDF...[/yellow]")
                try:
                    routine_query = f"SELECT ddl FROM `{database}.{schema}.INFORMATION_SCHEMA.ROUTINES` WHERE routine_name = '{name}'" if database else f"SELECT ddl FROM `{schema}.INFORMATION_SCHEMA.ROUTINES` WHERE routine_name = '{name}'"
                    res = list(bq_client.query(routine_query))
                    if res and res[0][0]:
                        ddl = res[0][0]
                        from mallard.transpiler import transpile_to_duckdb
                        duckdb_sql = transpile_to_duckdb(ddl)
                        try:
                            con.execute(duckdb_sql)
                            console.print(f"✅ [green]{source_id} (UDF)[/green]")
                        except duckdb.CatalogException as ex:
                            if "already exists" in str(ex):
                                console.print(f"✅ [dim]{source_id} (UDF cached)[/dim]")
                            else:
                                raise ex
                    else:
                        console.print(f"[bold red]Failed to hydrate {source_id}: Not found as Table or UDF.[/bold red]")
                except Exception as ex:
                    console.print(f"[bold red]Failed to hydrate {source_id} as UDF: {ex!s}[/bold red]")
            else:
                console.print(f"[bold red]Failed to hydrate {source_id}: {e!s}[/bold red]")

    con.close()
