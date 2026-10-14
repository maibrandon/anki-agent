import pytest
from anki.collection import Collection
from anki_agent.service import Service


@pytest.fixture
def col(tmp_path):
    collection = Collection(str(tmp_path / "collection.anki2"))
    yield collection
    collection.close()


@pytest.fixture
def service():
    return Service()


@pytest.fixture
def basic():
    return {"deck": "Default", "note_type": "Basic", "fields": {"Front": "What is MCP?", "Back": "Model Context Protocol"}, "tags": ["test"]}
