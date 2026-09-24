import networkx as nx


def _target_to_id(target: dict) -> str:
    """Helper to convert a target dict to a string ID."""
    if not target:
        return ""
    database = target.get("database", "")
    schema = target.get("schema", "")
    name = target.get("name", "")
    return f"{database}.{schema}.{name}" if database else f"{schema}.{name}"


def build_dag(compiled_graph: dict) -> nx.DiGraph:
    """
    Map parsed Dataform models into a NetworkX DAG.
    """
    dag = nx.DiGraph()

    # Collect all actions (tables, assertions, operations, declarations)
    actions = []
    for key in ["tables", "assertions", "operations", "declarations"]:
        for action in compiled_graph.get(key, []):
            # Backfill type for nodes that don't declare it explicitly (like declarations and operations)
            if "type" not in action:
                if key == "declarations":
                    action["type"] = "declaration"
                elif key == "operations":
                    action["type"] = "operation"
                elif key == "assertions":
                    action["type"] = "assertion"
            actions.append(action)

    # Add nodes
    for action in actions:
        target = action.get("target")
        if target:
            node_id = _target_to_id(target)
            dag.add_node(node_id, **action)
            # Add short name as an alias attribute for easier querying
            dag.nodes[node_id]["short_name"] = target.get("name")

    # Add edges based on dependencies
    for action in actions:
        target = action.get("target")
        if not target:
            continue

        node_id = _target_to_id(target)
        deps = action.get("dependencyTargets", [])

        for dep in deps:
            dep_id = _target_to_id(dep)
            if dep_id in dag:
                dag.add_edge(dep_id, node_id)

    return dag


def resolve_selection(
    dag: nx.DiGraph,
    select: str | None = None,
    tags: str | None = None,
    upstream: bool = False,
    downstream: bool = False,
) -> list[str]:
    """
    Resolve selection syntax (+model, model+, +model+, --tags) and boolean flags.
    Returns a list of node IDs to execute.
    """
    selected_nodes = set()
    initial_matches = set()

    if not select and not tags:
        # Default: return all nodes that are not declarations
        return [
            n for n, attr in dag.nodes(data=True) if attr.get("type") != "declaration"
        ]

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        for n, attr in dag.nodes(data=True):
            node_tags = attr.get("tags", [])
            if any(t in node_tags for t in tag_list):
                initial_matches.add(n)

    if select:
        selects = [s.strip() for s in select.split(",")]
        for s in selects:
            include_upstream = upstream or s.startswith("+")
            include_downstream = downstream or s.endswith("+")
            base_name = s.strip("+")

            # Find matching nodes
            matches = []
            for n, attr in dag.nodes(data=True):
                if (
                    n == base_name
                    or attr.get("short_name") == base_name
                    or n.endswith(f".{base_name}")
                ):
                    matches.append(n)

            # De-duplicate exactly identical matches (e.g. matched both n and short_name)
            matches = list(set(matches))

            if len(matches) > 1:
                # Ambiguous selection!
                import sys

                from rich.console import Console

                c = Console()
                c.print(
                    f"\n[bold red]Ambiguous selection for '{base_name}':[/bold red]"
                )
                c.print(
                    "[yellow]Multiple models match this name. Please be more specific by including the schema or database.[/yellow]"
                )
                for m in matches:
                    c.print(f"  - {m}")
                c.print()
                sys.exit(1)

            for match in matches:
                initial_matches.add(match)
                if include_upstream:
                    ancestors = nx.ancestors(dag, match)
                    selected_nodes.update(ancestors)
                if include_downstream:
                    descendants = nx.descendants(dag, match)
                    selected_nodes.update(descendants)

    # Apply global --upstream / --downstream to tag matches (or explicitly injected items)
    selected_nodes.update(initial_matches)

    if upstream:
        for match in list(initial_matches):
            selected_nodes.update(nx.ancestors(dag, match))

    if downstream:
        for match in list(initial_matches):
            selected_nodes.update(nx.descendants(dag, match))

    # Filter out declarations as they shouldn't be executed directly
    return [n for n in selected_nodes if dag.nodes[n].get("type") != "declaration"]
