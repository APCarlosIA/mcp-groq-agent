import pytest

from agente_mcp.servidor import crear_servidor


@pytest.fixture
def anyio_backend():
    """Ejecuta los tests asíncronos solo con asyncio."""
    return "asyncio"


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    """Servidor en memoria que guarda sus notas en una carpeta temporal."""
    monkeypatch.setenv("NOTAS_DIR", str(tmp_path / "notas"))
    return crear_servidor()
