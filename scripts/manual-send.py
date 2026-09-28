import subprocess
import sys
from pathlib import Path


project = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, str(project / "main.py"), "manual-send"],
    cwd=project,
)
raise SystemExit(result.returncode)
