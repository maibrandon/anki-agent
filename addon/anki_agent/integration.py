"""HTTP-to-Anki execution queue, including non-bypassable native approval."""
import threading

from aqt.operations import CollectionOp, QueryOp

from .confirmation import ask_deletion
from .deletion import DELETE_OPERATIONS
from .errors import AgentError
from .service import WriteResult


class Runner:
    def __init__(self, mw, service):
        self.mw, self.service = mw, service
        self.pending = threading.Lock()
        self.dialog = None

    def execute(self, operation, params):
        self.service.validate_request(operation, params)
        if not self.pending.acquire(blocking=False):
            raise AgentError("busy", "Anki is still processing the previous operation; retry shortly.")
        finished, cancelled = threading.Event(), threading.Event()
        outcome = {}

        def success(result):
            if finished.is_set():
                return
            outcome["result"] = result.payload if isinstance(result, WriteResult) else result
            self.pending.release()
            finished.set()

        def failure(exc):
            if finished.is_set():
                return
            outcome["error"] = exc if isinstance(exc, AgentError) else AgentError("anki_error", "Anki could not complete the operation.")
            self.pending.release()
            finished.set()

        def check_active(col):
            if cancelled.is_set():
                raise AgentError("timeout", "Request expired; nothing further will be deleted.")
            if self.mw.col is not col:
                raise AgentError("collection_changed", "The profile changed; preview again.")

        def normalize(result):
            if isinstance(result, WriteResult) and result.changes is None:
                from anki.collection import OpChanges
                result.changes = OpChanges()
            return result

        def start():
            try:
                col = self.mw.col
                check_active(col)
                if operation == "status":
                    return success(self.service.dispatch(col, operation, params))
                if col is None:
                    raise AgentError("collection_unavailable", "Open an Anki profile first.")

                def ordinary(active_col):
                    check_active(col)
                    if active_col is not col:
                        raise AgentError("collection_changed", "The collection changed; preview again.")
                    return normalize(self.service.dispatch(active_col, operation, params))

                if operation not in DELETE_OPERATIONS:
                    if operation in {"create_notes", "create_deck", "rename_deck", "move_cards"}:
                        CollectionOp(parent=self.mw, op=ordinary).success(success).failure(failure).run_in_background()
                    else:
                        QueryOp(parent=self.mw, op=ordinary, success=success).failure(failure).run_in_background()
                    return

                preview_id = params.get("preview_id")
                def prepare(active_col):
                    check_active(col)
                    if active_col is not col:
                        raise AgentError("collection_changed", "The collection changed; preview again.")
                    replay = self.service.deletions.replay(col, operation, preview_id)
                    if replay is not None:
                        return replay
                    return self.service.deletions.resolve(col, operation, preview_id)

                def ready(plan):
                    try:
                        check_active(col)
                        if isinstance(plan, dict):
                            return success(plan)  # Completed retry; no second prompt or write.
                        def confirmed():
                            self.dialog = None
                            try:
                                check_active(col)
                                grant = self.service.deletions.approve(col, operation, preview_id, plan)
                                def remove(active_col):
                                    check_active(col)
                                    if active_col is not col:
                                        raise AgentError("collection_changed", "The collection changed; preview again.")
                                    changes, payload = self.service.deletions.execute(
                                        col, operation, preview_id, grant, lambda: check_active(col))
                                    return WriteResult(changes, payload)
                                CollectionOp(parent=self.mw, op=remove).success(success).failure(failure).run_in_background()
                            except Exception as exc:
                                failure(exc)
                        def denied():
                            self.dialog = None
                            failure(AgentError("confirmation_denied", "Deletion cancelled or confirmation timed out; nothing was deleted."))
                        self.dialog = ask_deletion(self.mw, plan.summary, confirmed, denied)
                    except Exception as exc:
                        failure(exc)
                QueryOp(parent=self.mw, op=prepare, success=ready).failure(failure).run_in_background()
            except Exception as exc:
                failure(exc)

        self.mw.taskman.run_on_main(start)
        if not finished.wait(45):
            cancelled.set()
            raise AgentError("timeout", "Anki timed out. A running write may have completed; retry the same preview_id. Late confirmations cannot start a deletion.")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["result"]
