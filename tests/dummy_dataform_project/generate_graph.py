import json

graph = {
    "projectConfig": {
        "warehouse": "bigquery",
        "defaultSchema": "test_dataset",
        "assertionSchema": "test_dataset_assertions",
        "defaultDatabase": "test-project",
        "vars": {"date_id": "2023-01-01"},
        "defaultLocation": "US",
    },
    "tables": [
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "stg_events",
            },
            "type": "view",
            "query": "SELECT\n  id,\n  event_name\nFROM\n  `test-project.test_dataset.raw_events`\nWHERE\n  event_name != 'spam'",
            "dependencyTargets": [
                {
                    "database": "test-project",
                    "schema": "test_dataset",
                    "name": "raw_events",
                }
            ],
        },
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "dim_events",
            },
            "type": "table",
            "query": "SELECT\n  id,\n  event_name\nFROM\n  `test-project.test_dataset.stg_events`",
            "dependencyTargets": [
                {
                    "database": "test-project",
                    "schema": "test_dataset",
                    "name": "stg_events",
                }
            ],
        },
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "stg_users",
            },
            "type": "view",
            "tags": ["users"],
            "query": "SELECT\n  id,\n  event_name AS user_name\nFROM\n  `test-project.test_dataset.raw_users`",
            "dependencyTargets": [
                {
                    "database": "test-project",
                    "schema": "test_dataset",
                    "name": "raw_users",
                }
            ],
        },
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "dim_users",
            },
            "type": "table",
            "tags": ["users"],
            "query": "SELECT\n  id,\n  user_name\nFROM\n  `test-project.test_dataset.stg_users`",
            "dependencyTargets": [
                {
                    "database": "test-project",
                    "schema": "test_dataset",
                    "name": "stg_users",
                }
            ],
        },
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "fct_events",
            },
            "type": "incremental",
            "tags": ["events"],
            "query": "SELECT\n  id,\n  event_name\nFROM\n  `test-project.test_dataset.dim_events`",
            "incrementalQuery": "SELECT\n  id,\n  event_name\nFROM\n  `test-project.test_dataset.dim_events`",
            "dependencyTargets": [
                {
                    "database": "test-project",
                    "schema": "test_dataset",
                    "name": "dim_events",
                }
            ],
        },
    ],
    "assertions": [
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset_assertions",
                "name": "assert_pass",
            },
            "type": "assertion",
            "query": "SELECT 1 AS dummy LIMIT 0",
        },
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset_assertions",
                "name": "assert_fail",
            },
            "type": "assertion",
            "query": "SELECT 1 AS id",
        },
    ],
    "operations": [
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "create_udf",
            },
            "type": "operations",
            "queries": [
                "CREATE OR REPLACE FUNCTION `test-project.test_dataset.create_udf` (name STRING) RETURNS STRING AS (\n  CONCAT('user_', name)\n);"
            ],
        }
    ],
    "declarations": [
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "raw_events",
            }
        },
        {
            "target": {
                "database": "test-project",
                "schema": "test_dataset",
                "name": "raw_users",
            }
        },
    ],
}

with open("compiled_graph.json", "w") as f:
    json.dump(graph, f, indent=4)
