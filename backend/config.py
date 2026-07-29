from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
SRC_DIR = ROOT_DIR / "src"
API_KEY_FILE = ROOT_DIR / "ds.txt"
RS_PATH = ROOT_DIR / "data" / "relationship_state.json"
CONV_PATH = ROOT_DIR / "data" / "conversations.json"
STRATEGIES_DIR = ROOT_DIR / "strategies"

# SQLite + ChromaDB (embedded, zero-config)
DATA_DIR = str(ROOT_DIR / "data")

BASE_URL = "https://opencode.ai/zen/go/v1/chat/completions"
MODEL = "deepseek-v4-flash"



import sys
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def load_api_key() -> str:
    if not API_KEY_FILE.exists():
        raise FileNotFoundError(f"API Key file not found: {API_KEY_FILE}")
    content = API_KEY_FILE.read_text(encoding="utf-8").strip()
    return content.split("=")[-1].strip()
