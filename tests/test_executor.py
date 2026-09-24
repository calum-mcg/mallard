import duckdb
import networkx as nx

from mallard.executor import execute_dag, table_exists


def test_table_exists(tmp_path):
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE TABLE test_table (id INT)")

    assert table_exists(con, "test_table") is True
    assert table_exists(con, "missing_table") is False


def test_execute_dag_incremental(tmp_path, mocker):
    mocker.patch("mallard.executor.os.makedirs")
    mocker.patch("mallard.executor.duckdb.connect")

    dag = nx.DiGraph()
    dag.add_node(
        "proj.data.inc_model",
        type="incremental",
        query="SELECT * FROM source",
        incrementalQuery="SELECT * FROM source WHERE date > '2023-01-01'",
        uniqueKey=["id"],
        target={"schema": "data", "name": "inc_model"},
    )

    con_mock = mocker.MagicMock()
    mocker.patch("mallard.executor.duckdb.connect", return_value=con_mock)
    mocker.patch("mallard.executor.table_exists", return_value=True)
    mocker.patch("mallard.executor.transpile_to_duckdb", side_effect=lambda x: x)

    execute_dag(dag, ["proj.data.inc_model"], full_refresh=False)

    # Check that it did not drop and create the table since table_exists=True and full_refresh=False
    calls = [call[0][0].strip() for call in con_mock.execute.call_args_list]

    assert any("DELETE FROM data_inc_model" in call for call in calls)
    assert any(
        "INSERT INTO data_inc_model SELECT * FROM source WHERE date > '2023-01-01'"
        in call
        for call in calls
    )


def test_execute_dag_incremental_full_refresh(tmp_path, mocker):
    mocker.patch("mallard.executor.os.makedirs")

    dag = nx.DiGraph()
    dag.add_node(
        "proj.data.inc_model",
        type="incremental",
        query="SELECT * FROM source",
        target={"schema": "data", "name": "inc_model"},
    )

    con_mock = mocker.MagicMock()
    mocker.patch("mallard.executor.duckdb.connect", return_value=con_mock)
    mocker.patch("mallard.executor.table_exists", return_value=True)
    mocker.patch("mallard.executor.transpile_to_duckdb", side_effect=lambda x: x)

    execute_dag(dag, ["proj.data.inc_model"], full_refresh=True)

    calls = [call[0][0].strip() for call in con_mock.execute.call_args_list]
    assert any("DROP TABLE IF EXISTS data_inc_model" in call for call in calls)
    assert any(
        "CREATE TABLE data_inc_model AS SELECT * FROM source" in call for call in calls
    )


def test_execute_dag_assertion_failure(tmp_path, mocker):
    import pytest

    mocker.patch("mallard.executor.os.makedirs")

    dag = nx.DiGraph()
    dag.add_node(
        "proj.data.assert_model",
        type="assertion",
        query="SELECT * FROM table",
        target={"schema": "data", "name": "assert_model"},
    )

    con_mock = mocker.MagicMock()
    # Mock con.execute(..).fetchall() to return 1 row -> assertion failure
    con_mock.execute.return_value.fetchall.return_value = [{"id": 1}]
    mocker.patch("mallard.executor.duckdb.connect", return_value=con_mock)
    mocker.patch("mallard.executor.transpile_to_duckdb", side_effect=lambda x: x)

    with pytest.raises(SystemExit) as e:
        execute_dag(dag, ["proj.data.assert_model"])

    assert e.value.code == 1


def test_execute_dag_assertion_success(tmp_path, mocker):
    mocker.patch("mallard.executor.os.makedirs")

    dag = nx.DiGraph()
    dag.add_node(
        "proj.data.assert_model",
        type="assertion",
        query="SELECT * FROM table",
        target={"schema": "data", "name": "assert_model"},
    )

    con_mock = mocker.MagicMock()
    # Mock con.execute(..).fetchall() to return 0 rows -> assertion success
    con_mock.execute.return_value.fetchall.return_value = []
    mocker.patch("mallard.executor.duckdb.connect", return_value=con_mock)
    mocker.patch("mallard.executor.transpile_to_duckdb", side_effect=lambda x: x)

    # Should not raise SystemExit
    execute_dag(dag, ["proj.data.assert_model"])
