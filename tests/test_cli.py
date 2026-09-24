from typer.testing import CliRunner
from mallard.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Mallard" in result.stdout


def test_cli_clean(mocker):
    # Mock clean_cache
    mocker.patch("mallard.cli.clean_cache")
    result = runner.invoke(app, ["clean"])
    assert result.exit_code == 0
    assert "Cleaning Mallard cache" in result.stdout


def test_cli_run_full_refresh(mocker):
    mocker.patch("mallard.cli.compile_dataform", return_value={"tables": []})
    mocker.patch("mallard.cli.build_dag")
    mocker.patch("mallard.cli.resolve_selection", return_value=["node1"])
    mocker.patch("mallard.cli.hydrate_sources")
    mock_execute = mocker.patch("mallard.cli.execute_dag")

    result = runner.invoke(app, ["run", "--full-refresh"])
    assert result.exit_code == 0
    mock_execute.assert_called_once()
    assert mock_execute.call_args[1].get("full_refresh") is True
