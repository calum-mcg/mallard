import typer
from rich.console import Console
from rich.panel import Panel

from mallard.compiler import compile_dataform
from mallard.executor import clean_cache, execute_dag
from mallard.graph import build_dag, resolve_selection
from mallard.hydrator import get_config, hydrate_sources
from mallard.init_wizard import run_init_wizard

app = typer.Typer(
    help="Mallard: Fast local execution engine for Dataform powered by DuckDB",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.command("init")
def init():
    """
    Launch interactive CLI setup wizard to create .mallard.yml.
    """
    run_init_wizard()


@app.command("fetch")
def fetch(
    vars: str = typer.Option(
        None,
        "--vars",
        help="Inject variables into compilation, e.g. date_id=2023-01-01",
    ),
):
    """
    Pre-hydrate or update root BigQuery source partitions into local DuckDB.
    """
    with console.status("[bold blue]Compiling Dataform project...[/bold blue]"):
        compiled_graph = compile_dataform(vars=vars)
        dag = build_dag(compiled_graph)

    console.print("\n[bold blue]Hydrating sources...[/bold blue]")
    # Fetch for all nodes
    hydrate_sources(dag, list(dag.nodes()), compiled_graph=compiled_graph)


@app.command("run")
def run(
    select: str = typer.Option(
        None, "--select", help="Run specific models, e.g. +stg_orders+"
    ),
    tags: str = typer.Option(
        None, "--tags", help="Run models matching specified tags, e.g. core,hourly"
    ),
    upstream: bool = typer.Option(
        False, "--upstream", help="Include upstream dependencies for selected models"
    ),
    downstream: bool = typer.Option(
        False, "--downstream", help="Include downstream dependents for selected models"
    ),
    refresh_sources: bool = typer.Option(
        False,
        "--refresh-sources",
        help="Invalidate local DuckDB cache and re-fetch BigQuery partitions",
    ),
    full_refresh: bool = typer.Option(
        False, "--full-refresh", help="Force full rebuild of incremental models"
    ),
    vars: str = typer.Option(
        None,
        "--vars",
        help="Inject variables into compilation, e.g. date_id=2023-01-01",
    ),
):
    """
    Run compiled Dataform models locally on DuckDB.
    """
    if refresh_sources:
        console.print("[bold yellow]Refreshing sources...[/bold yellow]")
        clean_cache()

    with console.status(
        "[bold blue]Compiling Dataform project and building DAG...[/bold blue]"
    ):
        compiled_graph = compile_dataform(vars=vars)
        dag = build_dag(compiled_graph)
        selected_nodes = resolve_selection(
            dag, select=select, tags=tags, upstream=upstream, downstream=downstream
        )

    if not selected_nodes:
        console.print("[bold red]No models selected to run.[/bold red]")
        raise typer.Exit(1)

    console.print(
        f"[bold green]Selected {len(selected_nodes)} models to run.[/bold green]"
    )

    required_sources = set()
    for node in selected_nodes:
        for anc in dag.predecessors(node):
            if anc not in selected_nodes:
                required_sources.add(anc)

    types = {}
    for node_id in selected_nodes:
        t = dag.nodes[node_id].get("type", "unknown")
        types[t] = types.get(t, 0) + 1

    if required_sources:
        types["declaration"] = len(required_sources)

    summary = []
    if "declaration" in types:
        summary.append(f"{types['declaration']} sources")
    if "table" in types:
        summary.append(f"{types['table']} tables")
    if "view" in types:
        summary.append(f"{types['view']} views")
    if "incremental" in types:
        summary.append(f"{types['incremental']} incremental models")
    if "assertion" in types:
        summary.append(f"{types['assertion']} assertions")
    if "operation" in types:
        summary.append(f"{types['operation']} operations (UDFs)")

    summary_str = ", ".join(summary)

    config = get_config()
    row_limit = config.get("row_limit")
    limit_str = f"{row_limit} rows" if row_limit else "None"

    console.print(
        Panel(
            f"[bold]Date:[/bold] {vars if vars else 'Not specified'}\n"
            f"[bold]Limits:[/bold] {limit_str}\n"
            f"[bold]Nodes:[/bold] {summary_str}",
            title="[bold blue]Executing DAG on DuckDB[/bold blue]",
            border_style="blue",
        )
    )

    console.print("\n[bold blue]Hydrating sources...[/bold blue]")
    hydrate_sources(dag, selected_nodes, compiled_graph=compiled_graph)

    console.print("\n[bold blue]Processing models...[/bold blue]")
    execute_dag(dag, selected_nodes, full_refresh=full_refresh)
    console.print("[bold green]Execution completed successfully![/bold green]")


@app.command("iterate")
def iterate(
    var: str = typer.Option(
        ..., "--var", help="Variable name to iterate over, e.g. date_id"
    ),
    values: str = typer.Option(
        ...,
        "--values",
        help="Comma-separated values to iterate, e.g. 2023-01-01,2023-01-02",
    ),
    select: str = typer.Option(
        None, "--select", help="Run specific models, e.g. +stg_orders+"
    ),
    tags: str = typer.Option(
        None, "--tags", help="Run models matching specified tags, e.g. core,hourly"
    ),
    upstream: bool = typer.Option(
        False, "--upstream", help="Include upstream dependencies for selected models"
    ),
    downstream: bool = typer.Option(
        False, "--downstream", help="Include downstream dependents for selected models"
    ),
    refresh_sources: bool = typer.Option(
        False,
        "--refresh-sources",
        help="Invalidate local DuckDB cache and re-fetch BigQuery partitions before executing",
    ),
    full_refresh: bool = typer.Option(
        False, "--full-refresh", help="Force full rebuild of incremental models"
    ),
):
    """
    Run sequential iterations of models injecting different variable values.
    """
    if refresh_sources:
        console.print("[bold yellow]Refreshing sources...[/bold yellow]")
        clean_cache()

    val_list = [v.strip() for v in values.split(",")]

    for val in val_list:
        console.print(
            f"\n[bold magenta]--- Iteration: {var}={val} ---[/bold magenta]\n"
        )
        current_vars = f"{var}={val}"

        with console.status(
            f"[bold blue]Compiling Dataform project and building DAG for {var}={val}...[/bold blue]"
        ):
            compiled_graph = compile_dataform(vars=current_vars)
            dag = build_dag(compiled_graph)
            selected_nodes = resolve_selection(
                dag, select=select, tags=tags, upstream=upstream, downstream=downstream
            )

        if not selected_nodes:
            console.print(f"[bold red]No models selected to run for {val}.[/bold red]")
            continue

        console.print(
            f"[bold green]Selected {len(selected_nodes)} models to run.[/bold green]"
        )

        types = {}
        for node_id in selected_nodes:
            t = dag.nodes[node_id].get("type", "unknown")
            types[t] = types.get(t, 0) + 1

        summary = []
        if "table" in types:
            summary.append(f"{types['table']} tables")
        if "view" in types:
            summary.append(f"{types['view']} views")
        if "incremental" in types:
            summary.append(f"{types['incremental']} incremental models")
        if "assertion" in types:
            summary.append(f"{types['assertion']} assertions")
        if "operation" in types:
            summary.append(f"{types['operation']} operations")

        summary_str = ", ".join(summary)

        config = get_config()
        row_limit = config.get("row_limit")
        limit_str = f"{row_limit} rows" if row_limit else "None"

        console.print(
            Panel(
                f"[bold]Date:[/bold] {current_vars}\n"
                f"[bold]Limits:[/bold] {limit_str}\n"
                f"[bold]Nodes:[/bold] {summary_str}",
                title="[bold blue]Executing DAG on DuckDB[/bold blue]",
                border_style="blue",
            )
        )

        console.print("\n[bold blue]Hydrating sources...[/bold blue]")
        hydrate_sources(dag, selected_nodes, compiled_graph=compiled_graph)

        console.print("\n[bold blue]Processing models...[/bold blue]")
        execute_dag(dag, selected_nodes, full_refresh=full_refresh)

    console.print("\n[bold green]All iterations completed successfully![/bold green]")


@app.command("clean")
def clean():
    """
    Purge .mallard/ database cache and temporary artifacts.
    """
    console.print("[bold yellow]Cleaning Mallard cache...[/bold yellow]")
    clean_cache()
    console.print("[bold green]Cache cleaned.[/bold green]")


if __name__ == "__main__":
    app()
