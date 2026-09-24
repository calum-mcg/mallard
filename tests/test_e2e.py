import os
import shutil
from pathlib import Path

import pyarrow as pa
import pytest
import yaml
from typer.testing import CliRunner

from mallard.cli import app

runner = CliRunner()


@pytest.fixture
def dummy_project(tmp_path):
    """
    Copy the dummy_dataform_project to a temporary directory and change the current working directory to it.
    """
    source_dir = Path(__file__).parent / "dummy_dataform_project"
    dest_dir = tmp_path / "dummy_dataform_project"
    shutil.copytree(source_dir, dest_dir)

    original_cwd = os.getcwd()
    os.chdir(dest_dir)

    yield dest_dir
    os.chdir(original_cwd)


@pytest.fixture
def mock_bq_client(mocker):
    """
    Mock the BigQuery client and return a mock PyArrow table.
    """
    mock_arrow_table = pa.Table.from_pydict(
        {"id": [1, 2, 3], "event_name": ["click", "view", "spam"]}
    )

    mock_client = mocker.MagicMock()
    mock_query_job = mocker.MagicMock()
    mock_query_job.to_arrow.return_value = mock_arrow_table
    mock_client.query.return_value = mock_query_job

    mocker.patch("mallard.hydrator.bigquery.Client", return_value=mock_client)

    return mock_client


def test_e2e_init(dummy_project, mocker):
    """
    Test that mallard init generates .mallard.yml using defaults from workflow_settings.yaml
    """
    # Mock questionary to return the default values it receives
    mock_text = mocker.patch("mallard.init_wizard.questionary.text")

    # Configure mock to return the default value it was called with
    def mock_ask():
        return mock_text.call_args[1].get("default", "")

    mock_text.return_value.ask.side_effect = mock_ask

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0

    config_path = Path(".mallard.yml")
    assert config_path.exists()

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    assert config["project_id"] == "test-project"
    assert config["dataset"] == "test_dataset"
    assert config["row_limit"] == 1000
    assert "partition_filters" in config
    assert "example_source_name" in config["partition_filters"]


@pytest.fixture
def mock_compile_dataform(mocker):
    """
    Mock Dataform CLI compilation to bypass Node 20+ issues with Dataform core.
    Returns the pre-compiled graph json.
    """
    import json

    def _mock_compile(*args, **kwargs):
        with open("compiled_graph.json", "r") as f:
            return json.load(f)

    mocker.patch("mallard.cli.compile_dataform", side_effect=_mock_compile)
    return _mock_compile


def test_e2e_duckdb_output(dummy_project, mock_bq_client, mock_compile_dataform):
    """
    Test compilation, transpilation, DuckDB execution and that output table contains expected filtered data.
    """
    import duckdb

    # Setup minimal config needed for execution
    config = {
        "project_id": "test-project",
        "dataset": "test_dataset",
        "row_limit": 1000,
    }
    with open(".mallard.yml", "w") as f:
        yaml.dump(config, f)

    result = runner.invoke(app, ["run", "--select", "+dim_events"])
    print(result.stdout)
    if result.exception:
        print(result.exception)

    assert result.exit_code == 0

    con = duckdb.connect(".mallard/cache.duckdb")
    rows = con.execute("SELECT * FROM test_dataset_dim_events").fetchall()
    con.close()

    # stg_events filters out 'spam', so we expect 2 rows remaining from the 3 mock rows
    assert len(rows) == 2
    event_names = [row[1] for row in rows]
    assert "spam" not in event_names


def test_e2e_assertion_pass(dummy_project, mock_bq_client, mock_compile_dataform):
    """
    Test that an assertion returning 0 rows passes (exit code 0).
    """
    # Setup minimal config needed for execution
    config = {
        "project_id": "test-project",
        "dataset": "test_dataset",
        "row_limit": 1000,
    }
    with open(".mallard.yml", "w") as f:
        yaml.dump(config, f)

    result = runner.invoke(app, ["run", "--select", "+assert_pass"])

    assert result.exit_code == 0
    assert "✅ test-project.test_dataset_assertions.assert_pass" in result.stdout


def test_e2e_assertion_fail(dummy_project, mock_bq_client, mock_compile_dataform):
    """
    Test that an assertion returning >0 rows fails and aborts execution (exit code 1).
    """
    # Setup minimal config needed for execution
    config = {
        "project_id": "test-project",
        "dataset": "test_dataset",
        "row_limit": 1000,
    }
    with open(".mallard.yml", "w") as f:
        yaml.dump(config, f)

    result = runner.invoke(app, ["run", "--select", "+assert_fail"])

    assert result.exit_code == 1
    assert (
        "Assertion test-project.test_dataset_assertions.assert_fail failed"
        in result.stdout
    )
    assert "Returned 1 failing rows" in result.stdout
