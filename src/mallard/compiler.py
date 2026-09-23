import json
import subprocess

from rich.console import Console

console = Console()

class CompilationError(Exception):
    pass

def compile_dataform(vars: str | None = None):
    """
    Invokes `npx @dataform/cli compile --json` via subprocess to extract target
    definitions, JS macros, tags, dependencies, and upstream declarations.
    """
    try:
        args = ["npx", "@dataform/cli", "compile", "--json"]
        if vars:
            args.append(f"--vars={vars}")
            
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Dataform compilation failed:[/bold red]\n{e.stderr}")
        raise CompilationError("Failed to compile Dataform project.") from e
    except FileNotFoundError as e:
        console.print("[bold red]npx command not found. Ensure Node.js and npm are installed.[/bold red]")
        raise CompilationError("npx not found.") from e
    except json.JSONDecodeError as e:
        console.print("[bold red]Failed to parse Dataform compilation output as JSON.[/bold red]")
        raise CompilationError("Invalid JSON from compilation.") from e
