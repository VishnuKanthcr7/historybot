"""Chroma persistence settings. Embeddings come from Ollama, not Chroma's default model."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_PATH = PROJECT_ROOT / "data" / "chroma"
CHUNKS_PATH = PROJECT_ROOT / "data" / "extracted" / "chapter5_chunks.json"

COLLECTION_NAME = "historybot_class9_ss"
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_HOST = "http://127.0.0.1:11434"
CHAT_TOP_K = 5
ECONTENT_TOP_K = 12
EXPECTED_CHUNK_COUNT = 67
ALLOWED_CHAPTER = "THE MOGHULS AND THE MARATHAS"
