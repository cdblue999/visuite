import sys
import os
from pathlib import Path

INGECAD_ROOT = Path(os.environ.get("INGECAD_ROOT", "/home/elinux/ingecad"))
sys.path.insert(0, str(INGECAD_ROOT.resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
