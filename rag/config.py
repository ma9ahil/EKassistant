from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHROMA_DIR = ROOT_DIR / ".chroma"
SEED_URLS_PATH = DATA_DIR / "gitlab_seed_urls.txt"
FEEDBACK_PATH = ROOT_DIR / "feedback.csv"

COLLECTION_NAME = "gitlab_handbook"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_TOP_K = 5
MIN_RELEVANCE_SCORE = 0.28
