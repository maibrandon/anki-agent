"""Build a reproducible .ankiaddon without caches or credentials."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / "dist" / "anki-agent-0.2.0.ankiaddon"
output.parent.mkdir(exist_ok=True)
files = sorted(p for p in (root / "addon").rglob("*.py") if "user_files" not in p.parts and "__pycache__" not in p.parts) + [root / "addon" / "manifest.json"]
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        info = zipfile.ZipInfo(path.relative_to(root / "addon").as_posix(), (2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, path.read_bytes())
    for name in ("LICENSE", "NOTICE"):
        if (root / name).exists():
            archive.writestr(name, (root / name).read_bytes())
print(output)
