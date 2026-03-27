import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE_SRC = ROOT / "services" / "ingestion-service" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))
