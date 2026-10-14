"""Recovery packages exported through the open collection API, never live SQLite."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import zipfile

from .errors import AgentError


def create_recovery_backup(col, root):
    if root is None:
        raise AgentError("backup_unavailable", "Backup storage is not configured; nothing was deleted.")
    # Separate profile directories without exposing profile names in filenames.
    profile = hashlib.sha256(str(col.path).encode()).hexdigest()[:16]
    folder = Path(root) / profile
    temporary = None
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(folder.parent, 0o700)
        os.chmod(folder, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = folder / f"anki-agent-{stamp}-{secrets.token_hex(8)}.apkg"
        temporary = destination.with_suffix(".partial.apkg")
        from anki.collection import ExportAnkiPackageOptions
        count = col.export_anki_package(
            out_path=str(temporary),
            options=ExportAnkiPackageOptions(with_scheduling=True, with_deck_configs=True, with_media=True),
            limit=None,
        )
        os.chmod(temporary, 0o600)
        with zipfile.ZipFile(temporary, "a", compression=zipfile.ZIP_DEFLATED) as package:
            # Standard .apkg imports omit empty decks. Preserve all deck metadata
            # as an inspectable sidecar inside the same immutable recovery file.
            package.writestr("anki-agent-recovery.json", json.dumps({
                "version": 1, "decks": col.decks.get_all_legacy(),
                "deck_configs": col.decks.all_config(),
                "notice": "Anki imports the standard package contents. Empty decks can be recreated using this metadata or recovered with Undo."
            }, ensure_ascii=False))
            if package.testzip() is not None or not package.namelist():
                raise ValueError("Invalid backup archive")
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        temporary.rename(destination)
        return {"path": str(destination), "format": "apkg", "exported_notes": count,
                "includes_media": True, "includes_scheduling": True, "includes_deck_metadata": True,
                "scope": "All notes/cards, associated decks and note types; excludes collection preferences and add-on settings."}
    except Exception:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise AgentError("backup_failed", "Recovery backup could not be completed; nothing was deleted. Check free disk space and backup folder permissions.") from None
