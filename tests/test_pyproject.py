import tomllib
from pathlib import Path


def test_pyproject_sem_pino_de_url():
    dados = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    deps = dados["project"]["dependencies"]
    assert any(d.startswith("tcm-ui") for d in deps)
    assert not [d for d in deps if "@" in d]
