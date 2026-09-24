from mallard.transpiler import transpile_to_duckdb


def test_transpile_basic():
    # Should stay relatively unchanged but normalized
    result = transpile_to_duckdb("SELECT * FROM my_table")
    assert "SELECT" in result
    assert "my_table" in result


def test_transpile_table_flattening():
    # Should convert catalog.schema.table to schema_table
    sql = "SELECT * FROM `my-proj.my_dataset.my_table`"
    result = transpile_to_duckdb(sql)
    assert "my_dataset_my_table" in result
    assert "my-proj" not in result


def test_transpile_table_flattening_with_alias():
    # Should preserve aliases
    sql = "SELECT t.id FROM `my_dataset.my_table` AS t"
    result = transpile_to_duckdb(sql)
    assert "my_dataset_my_table AS t" in result


def test_transpile_join_flattening():
    # Should convert both tables in a join
    sql = "SELECT * FROM `db1.table1` a JOIN `proj2.db2.table2` b ON a.id = b.id"
    result = transpile_to_duckdb(sql)
    assert "db1_table1 AS a" in result
    assert "db2_table2 AS b" in result


def test_transpile_invalid():
    # Invalid SQL should return as-is if parsing fully throws Exception
    result = transpile_to_duckdb("SELECT ) ) ) ) FROM FROM")
    assert result == "SELECT ) ) ) ) FROM FROM"


def test_transpile_to_duckdb():
    bq_sql = "SELECT current_timestamp() AS ts, extract(year FROM date) as yr"
    duckdb_sql = transpile_to_duckdb(bq_sql)

    assert "CURRENT_TIMESTAMP" in duckdb_sql.upper()
    assert "EXTRACT" in duckdb_sql.upper()


def test_transpile_bq_specific():
    # BigQuery specific string aggregation syntax
    bq_sql = "SELECT string_agg(name, ', ') FROM users"
    duckdb_sql = transpile_to_duckdb(bq_sql)

    assert duckdb_sql is not None
