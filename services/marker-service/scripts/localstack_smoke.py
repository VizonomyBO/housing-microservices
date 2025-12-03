"""Simple CLI to verify LocalStack connectivity for marker-service."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aws_runtime import build_client, describe_runtime, load_runtime_config


def main() -> int:
    config = load_runtime_config()
    print(f"AWS runtime: {describe_runtime(config)}")

    try:
        s3 = build_client("s3", runtime=config)
        response = s3.list_buckets()
        bucket_names = [bucket["Name"] for bucket in response.get("Buckets", [])]
        print(json.dumps({"bucket_count": len(bucket_names), "buckets": bucket_names}))
        return 0
    except Exception as exc:  # pragma: no cover - smoke helper
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
