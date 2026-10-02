import importlib.util
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/00_check_api_environment.py"


def _module():
    spec = importlib.util.spec_from_file_location("api_env_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_environment_check_reports_presence_without_values(monkeypatch):
    module = _module()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "do-not-emit-this-value")
    result = module.status()
    assert result["v9_live_ready"] is True
    assert result["secret_values_read_or_printed"] is False
    assert result["variables"]["DASHSCOPE_API_KEY"]["status"] == "PRESENT"
    assert "do-not-emit-this-value" not in str(result)
