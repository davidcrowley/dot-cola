from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout

from app.services.processing_service import run_ocr_pipeline


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        with redirect_stdout(io.StringIO()):
            result = run_ocr_pipeline(
                combined_image_path=payload["combined_image_path"],
                targets=payload["targets"],
                match_threshold=int(payload["match_threshold"]),
            )
    except Exception as exc:
        sys.stdout.write(json.dumps({"error": str(exc)}))
        return 1

    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
