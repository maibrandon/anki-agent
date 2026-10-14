"""Human-owned confirmation surface. No approval RPC or auto-accept option."""
import json
from aqt.qt import QMessageBox, QTimer, Qt


def ask_deletion(parent, summary, yes, no, timeout_ms=30_000):
    box = QMessageBox(parent)
    box.setWindowTitle("Anki Agent — confirm deletion")
    box.setTextFormat(Qt.TextFormat.PlainText)
    scope = f"Delete exactly {summary['card_count']} card(s) and {summary['note_count_deleted']} orphaned note(s)?"
    if summary["operation"] == "delete_deck":
        names = "\n".join(f"{d['name']} (ID {d['id']})" for d in summary["decks"])
        scope = f"Delete these {summary['deck_count']} deck(s), including subdecks?\n{names}\n\n" + scope
    else:
        scope += "\nCard IDs: " + ", ".join(str(i) for i in summary["card_ids"])
    box.setText(scope)
    box.setInformativeText("Only click Yes if you explicitly want this deletion. A recovery backup must finish first. Other sibling cards are preserved. No or closing this window cancels. This request expires shortly.")
    box.setDetailedText(json.dumps(summary, indent=2, ensure_ascii=False))
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setEscapeButton(QMessageBox.StandardButton.No)
    timer = QTimer(box)
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: box.done(int(QMessageBox.StandardButton.No)))
    def finished(result):
        timer.stop()
        if result == int(QMessageBox.StandardButton.Yes):
            yes()
        else:
            no()
        box.deleteLater()
    box.finished.connect(finished)
    # Keep a Python reference while the non-modal dialog is visible.
    box._anki_agent_timer = timer
    box.open()
    timer.start(timeout_ms)
    return box
