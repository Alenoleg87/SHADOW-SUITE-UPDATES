"""SHADOW SUITE PRO - System Diagnostic Module."""

import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

MODULE_VERSION = "1.0.0"
MODULE_NAME = "System Diagnostic"


def run_diagnostic():
    return {
        "module": MODULE_NAME,
        "version": MODULE_VERSION,
        "status": "SUCCESS",
        "python": platform.python_version(),
        "system": platform.system(),
        "architecture": platform.machine(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file_exists": Path(__file__).is_file(),
    }


if __name__ == "__main__":
    for key, value in run_diagnostic().items():
        print(f"{key}: {value}")