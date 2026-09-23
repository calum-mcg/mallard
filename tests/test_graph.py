from mallard.graph import build_dag, resolve_selection

def test_build_dag():
    compiled_graph = {
        "tables": [
            {
                "target": {"database": "proj", "schema": "data", "name": "stg_orders"},
                "dependencyTargets": [{"database": "proj", "schema": "data", "name": "raw_orders"}]
            },
            {
                "target": {"database": "proj", "schema": "data", "name": "fct_orders"},
                "dependencyTargets": [{"database": "proj", "schema": "data", "name": "stg_orders"}]
            }
        ],
        "declarations": [
            {
                "target": {"database": "proj", "schema": "data", "name": "raw_orders"}
            }
        ]
    }
    
    dag = build_dag(compiled_graph)
    
    assert len(dag.nodes) == 3
    assert "proj.data.fct_orders" in dag.nodes
    assert dag.has_edge("proj.data.raw_orders", "proj.data.stg_orders")
    assert dag.has_edge("proj.data.stg_orders", "proj.data.fct_orders")

def test_resolve_selection():
    compiled_graph = {
        "tables": [
            {"target": {"database": "my_proj", "schema": "data", "name": "stg_orders"}, "type": "table", "tags": ["core"]},
            {"target": {"database": "my_proj", "schema": "data", "name": "fct_orders"}, "type": "table", "dependencyTargets": [{"database": "my_proj", "schema": "data", "name": "stg_orders"}]},
            {"target": {"database": "my_proj", "schema": "data", "name": "mart_orders"}, "type": "table", "dependencyTargets": [{"database": "my_proj", "schema": "data", "name": "fct_orders"}]}
        ]
    }
    dag = build_dag(compiled_graph)
    
    # Test --tags
    selected = resolve_selection(dag, tags="core")
    assert len(selected) == 1
    assert selected[0] == "my_proj.data.stg_orders"
    
    # Test +model (short_name)
    selected = resolve_selection(dag, select="+fct_orders")
    assert len(selected) == 2
    assert "my_proj.data.stg_orders" in selected
    assert "my_proj.data.fct_orders" in selected
    
    # Test model+ (schema.name)
    selected = resolve_selection(dag, select="data.stg_orders+")
    assert len(selected) == 3
    assert "my_proj.data.mart_orders" in selected

    # Test --upstream boolean (database.schema.name)
    selected = resolve_selection(dag, select="my_proj.data.fct_orders", upstream=True)
    assert len(selected) == 2
    assert "my_proj.data.stg_orders" in selected
    
    # Test --downstream boolean (short_name)
    selected = resolve_selection(dag, select="stg_orders", downstream=True)
    assert len(selected) == 3
    assert "my_proj.data.mart_orders" in selected

def test_ambiguous_selection(mocker):
    import pytest
    compiled_graph = {
        "tables": [
            {"target": {"database": "my_proj", "schema": "schema1", "name": "stg_orders"}, "type": "table"},
            {"target": {"database": "my_proj", "schema": "schema2", "name": "stg_orders"}, "type": "table"}
        ]
    }
    dag = build_dag(compiled_graph)
    
    with pytest.raises(SystemExit) as e:
        resolve_selection(dag, select="stg_orders")
    
    assert e.value.code == 1
