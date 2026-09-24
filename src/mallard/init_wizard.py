from pathlib import Path

import questionary
import yaml
from rich.console import Console

console = Console()


def run_init_wizard():
    """
    Interactive CLI setup wizard to create .mallard.yml.
    """
    console.print(
        "\n[bold cyan]🦆 Welcome to Mallard Initialization Wizard[/bold cyan]\n"
    )

    # Pre-parse workflow_settings.yaml to suggest defaults
    default_project = ""
    default_dataset = ""
    has_vars = False

    wf_settings_path = Path("workflow_settings.yaml")
    if wf_settings_path.exists():
        try:
            with open(wf_settings_path, "r") as f:
                wf_settings = yaml.safe_load(f)
                if wf_settings:
                    default_project = wf_settings.get("defaultProject", "")
                    default_dataset = wf_settings.get("defaultDataset", "")
                    has_vars = "vars" in wf_settings
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not parse workflow_settings.yaml to suggest defaults: {e}[/yellow]"
            )

    project_id = questionary.text(
        "What is your BigQuery Project ID?", default=default_project
    ).ask()
    if project_id is None:
        console.print("[bold red]Operation cancelled by user. Aborting.[/bold red]")
        return
    if not project_id.strip():
        console.print("[bold red]Project ID is required. Aborting.[/bold red]")
        return

    dataset = questionary.text(
        "What is the default dataset?", default=default_dataset
    ).ask()
    if dataset is None:
        console.print("[bold red]Operation cancelled by user. Aborting.[/bold red]")
        return

    row_limit = questionary.text(
        "What is the default row limit for local execution? (e.g. 1000)", default="1000"
    ).ask()
    if row_limit is None:
        console.print("[bold red]Operation cancelled by user. Aborting.[/bold red]")
        return

    try:
        row_limit = int(row_limit)
    except ValueError:
        console.print("[bold red]Invalid row limit. Using 1000.[/bold red]")
        row_limit = 1000

    config = {
        "project_id": project_id,
        "dataset": dataset,
        "row_limit": row_limit,
    }

    if has_vars:
        config["partition_filters"] = {
            "example_source_name": "date_column = '{var_name}'"
        }
        console.print(
            "[blue]Detected vars in workflow_settings.yaml. Added example partition_filters to .mallard.yml.[/blue]"
        )

    config_path = Path(".mallard.yml")
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    console.print(f"[bold green]Successfully generated {config_path}[/bold green]")

    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if ".mallard/" not in content:
            with open(gitignore_path, "a") as f:
                f.write("\n# Mallard cache\n.mallard/\n")
            console.print("[bold green]Added .mallard/ to .gitignore[/bold green]")
    else:
        with open(gitignore_path, "w") as f:
            f.write("# Mallard cache\n.mallard/\n")
        console.print("[bold green]Created .gitignore and added .mallard/[/bold green]")
