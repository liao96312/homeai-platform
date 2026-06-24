from pathlib import Path
from threading import Lock
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.app.core.config import settings

_client: Any | None = None
_client_lock = Lock()


def get_chroma_client() -> Any:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                persist_dir = settings.chroma_persist_dir or "./chroma_data"
                Path(persist_dir).mkdir(parents=True, exist_ok=True)
                _client = chromadb.PersistentClient(
                    path=persist_dir,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
    return _client
