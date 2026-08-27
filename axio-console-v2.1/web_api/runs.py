from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterator


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunState:
    id: str
    conversation_id: str
    mode: str
    status: str = "queued"
    events: list[dict] = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    condition: threading.Condition = field(default_factory=threading.Condition)


@dataclass
class ApprovalState:
    id: str
    run_id: str
    action: str
    detail: dict
    decision: str = "pending"
    note: str = ""
    signal: threading.Event = field(default_factory=threading.Event)


class RunManager:
    def __init__(self):
        self._runs: dict[str, RunState] = {}
        self._approvals: dict[str, ApprovalState] = {}
        self._lock = threading.RLock()

    def create(self, conversation_id: str, mode: str, worker: Callable) -> RunState:
        run = RunState(str(uuid.uuid4()), conversation_id, mode)
        with self._lock:
            self._runs[run.id] = run
        thread = threading.Thread(target=self._execute, args=(run, worker), daemon=True)
        thread.start()
        return run

    def _execute(self, run: RunState, worker: Callable) -> None:
        run.status = "running"
        self.emit(run.id, "run_started", {"mode": run.mode})
        try:
            worker(run)
            if run.cancel.is_set():
                run.status = "cancelled"
                self.emit(run.id, "run_cancelled", {})
            elif run.status not in TERMINAL_STATUSES:
                run.status = "completed"
                self.emit(run.id, "run_completed", {})
        except Exception as exc:
            run.status = "failed"
            self.emit(run.id, "error", {"message": str(exc)})
        finally:
            with run.condition:
                run.condition.notify_all()

    def get(self, run_id: str) -> RunState:
        run = self._runs.get(run_id)
        if not run:
            raise KeyError(run_id)
        return run

    def summary(self, run_id: str) -> dict:
        run = self.get(run_id)
        return {
            "id": run.id,
            "conversation_id": run.conversation_id,
            "mode": run.mode,
            "status": run.status,
            "event_count": len(run.events),
        }

    def emit(self, run_id: str, event_type: str, data: dict) -> dict:
        run = self.get(run_id)
        with run.condition:
            event = {
                "type": event_type,
                "run_id": run.id,
                "sequence": len(run.events) + 1,
                "timestamp": now_iso(),
                "data": data,
            }
            run.events.append(event)
            run.condition.notify_all()
            return event

    def stream(self, run_id: str, after: int = 0) -> Iterator[str]:
        run = self.get(run_id)
        cursor = max(0, after)
        while True:
            with run.condition:
                while cursor >= len(run.events) and run.status not in TERMINAL_STATUSES:
                    run.condition.wait(timeout=15)
                    if cursor >= len(run.events):
                        yield ": keepalive\n\n"
                pending = run.events[cursor:]
            for event in pending:
                cursor += 1
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            if run.status in TERMINAL_STATUSES and cursor >= len(run.events):
                break

    def cancel(self, run_id: str) -> dict:
        run = self.get(run_id)
        run.cancel.set()
        return self.summary(run_id)

    def request_approval(
        self,
        run: RunState,
        action: str,
        detail: dict,
        timeout: float = 900,
    ) -> ApprovalState:
        approval = ApprovalState(str(uuid.uuid4()), run.id, action, detail)
        with self._lock:
            self._approvals[approval.id] = approval
        self.emit(
            run.id,
            "approval_required",
            {
                "approval_id": approval.id,
                "action": action,
                "detail": detail,
            },
        )
        elapsed = 0.0
        while elapsed < timeout and not run.cancel.is_set():
            if approval.signal.wait(timeout=0.25):
                return approval
            elapsed += 0.25
        approval.decision = "denied"
        approval.note = "Approval timed out or run was cancelled."
        return approval

    def resolve_approval(self, approval_id: str, decision: str, note: str = "") -> dict:
        approval = self._approvals.get(approval_id)
        if not approval:
            raise KeyError(approval_id)
        if approval.decision != "pending":
            return self.approval_summary(approval)
        approval.decision = decision
        approval.note = note
        approval.signal.set()
        self.emit(
            approval.run_id,
            "approval_resolved",
            {
                "approval_id": approval.id,
                "decision": decision,
                "note": note,
            },
        )
        return self.approval_summary(approval)

    @staticmethod
    def approval_summary(approval: ApprovalState) -> dict:
        return {
            "id": approval.id,
            "run_id": approval.run_id,
            "action": approval.action,
            "detail": approval.detail,
            "decision": approval.decision,
            "note": approval.note,
        }

