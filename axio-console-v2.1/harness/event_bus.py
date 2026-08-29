"""
AXIO Harness -- Event Bus  (Plan Fase C · C7)

Agents never call each other in code. They publish messages to this central bus
which the orchestrator owns and routes. That gives the orchestrator total
visibility (every message is logged in `history`) while keeping communication
fast — a publisher does not wait on the orchestrator to continue.

Messages carry a priority. The bus delivers `critical` before `normal` before
`background`, FIFO within a priority. A PEER_REQUEST whose target subscriber
returns a dict is automatically answered with a correlated PEER_RESPONSE.

Delivery is driven explicitly by `pump()` (the orchestrator's routing tick), so
behaviour is deterministic and unit-testable with no threads or wall-clock. The
internals are lock-guarded so real ThreadPoolExecutor workers can publish safely.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Callable

PEER_REQUEST, PEER_RESPONSE = "PEER_REQUEST", "PEER_RESPONSE"

# Lower rank is delivered first.
_PRIORITY_RANK = {"critical": 0, "normal": 1, "background": 2}


@dataclass(frozen=True)
class Message:
    sender: str
    target: str
    msg_type: str
    payload: dict
    priority: str = "normal"
    correlation_id: str = ""
    seq: int = 0


Subscriber = Callable[[Message], dict | None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, Subscriber] = {}
        self._queue: list[Message] = []
        self._counter = itertools.count(1)
        self._corr = itertools.count(1)
        self._lock = threading.Lock()
        self.history: list[Message] = []      # full audit log for the orchestrator

    # ── wiring ──────────────────────────────────────────────────────────────
    def subscribe(self, agent: str, callback: Subscriber) -> None:
        with self._lock:
            self._subs[agent] = callback

    def publish(self, sender: str, target: str, msg_type: str, payload: dict,
                priority: str = "normal", correlation_id: str | None = None) -> str:
        if priority not in _PRIORITY_RANK:
            raise ValueError(f"Unknown priority '{priority}'")
        with self._lock:
            cid = correlation_id or f"cid-{next(self._corr)}"
            msg = Message(sender, target, msg_type, dict(payload), priority,
                          cid, next(self._counter))
            self._queue.append(msg)
            self.history.append(msg)
            return cid

    # ── routing ─────────────────────────────────────────────────────────────
    def _drain_sorted(self) -> list[Message]:
        # Priority first, then FIFO (seq) — sole place ordering is decided.
        batch = sorted(self._queue, key=lambda m: (_PRIORITY_RANK[m.priority], m.seq))
        self._queue = []
        return batch

    def pump(self) -> int:
        """Deliver all queued messages to their target subscribers.

        Returns the number of messages delivered. A PEER_REQUEST whose target
        returns a dict yields an auto-published PEER_RESPONSE back to the sender
        (queued for the next pump). Delivery to an unknown target is dropped but
        still recorded in history. Loops until the queue is empty so a response
        published during delivery is itself delivered in the same pump.
        """
        delivered = 0
        while True:
            with self._lock:
                if not self._queue:
                    return delivered
                batch = self._drain_sorted()
            for msg in batch:
                sub = self._subs.get(msg.target)
                if sub is None:
                    continue
                result = sub(msg)
                delivered += 1
                if msg.msg_type == PEER_REQUEST and isinstance(result, dict):
                    self.publish(sender=msg.target, target=msg.sender,
                                 msg_type=PEER_RESPONSE, payload=result,
                                 priority=msg.priority,
                                 correlation_id=msg.correlation_id)

    def responses_for(self, correlation_id: str) -> list[Message]:
        return [m for m in self.history
                if m.correlation_id == correlation_id and m.msg_type == PEER_RESPONSE]
