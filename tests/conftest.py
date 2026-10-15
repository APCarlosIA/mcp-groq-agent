import pytest


@pytest.fixture
def anyio_backend():
    """Ejecuta los tests asíncronos solo con asyncio."""
    return "asyncio"