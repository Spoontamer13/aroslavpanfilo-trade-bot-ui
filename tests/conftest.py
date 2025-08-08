# tests/conftest.py
import os
import sys
import pytest

# Добавим корень репозитория (один уровень выше tests/) в PYTHONPATH
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

@pytest.fixture(autouse=True)
def anyio_backend():
    return 'asyncio'