"""Making a run survive the process that started it.

Three tables, and only one of them is interesting.

`outcomes` and `events` are convenience: an outcome serialises to a single JSON
document because it is read and written as a unit, and events are kept apart
because the UI replays them.

`calls` is the one that matters. It is a **ledger of phone calls placed**, and
it is written *before* the dial, not after. A process that forgets what it
dialled will dial again, and the person on the other end has no way of knowing
that the second call is a bug rather than a second request. Recording it
afterwards would leave exactly the window that matters uncovered: the crash
that happens while the phone is ringing.

So the sequence is claim, dial, complete. Each state means something specific
on restart:

* no row            - never dialled. Safe to dial.
* claimed, no result - a call was started and we do not know how it ended.
                       Refuse to re-dial; a human has to look.
* claimed + result   - the call finished. Replay the stored result; dial nothing.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .calle import CallOutcome
from .models import Outcome, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
  id          TEXT PRIMARY KEY,
  goal        TEXT NOT NULL,
  status      TEXT NOT NULL,
  document    TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  outcome_id  TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  at          TEXT NOT NULL,
  kind        TEXT NOT NULL,
  payload     TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS events_seq ON events (outcome_id, seq);

CREATE TABLE IF NOT EXISTS calls (
  idempotency_key TEXT PRIMARY KEY,
  outcome_id      TEXT NOT NULL,
  action_id       TEXT NOT NULL,
  phone           TEXT NOT NULL,
  status          TEXT NOT NULL,
  call_id         TEXT,
  result          TEXT,
  claimed_at      TEXT NOT NULL,
  completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS calls_outcome ON calls (outcome_id);
"""


@dataclass
class LedgerEntry:
    idempotency_key: str
    outcome_id: str
    action_id: str
    phone: str
    status: str
    call_id: str | None
    result: dict[str, Any] | None
    claimed_at: str
    completed_at: str | None

    @property
    def finished(self) -> bool:
        return self.result is not None

    def replay(self) -> CallOutcome:
        """Rebuild the CallOutcome this key already produced."""
        assert self.result is not None
        return CallOutcome(
            call_id=self.call_id or "",
            status=self.status,
            structured=self.result.get("structured") or {},
            raw={"replayed_from_ledger": True, **(self.result.get("raw") or {})},
        )


class Store:
    def __init__(self, path: str | Path = "outcome.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- outcomes --------------------------------------------------------

    def save(self, outcome: Outcome) -> None:
        self._db.execute(
            """INSERT INTO outcomes (id, goal, status, document, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 goal=excluded.goal, status=excluded.status,
                 document=excluded.document, updated_at=excluded.updated_at""",
            (
                outcome.id,
                outcome.goal,
                outcome.status.value,
                json.dumps(outcome.to_dict()),
                outcome.created_at,
                outcome.updated_at,
            ),
        )
        self._db.commit()

    def load(self, outcome_id: str) -> Outcome | None:
        row = self._db.execute(
            "SELECT document FROM outcomes WHERE id = ?", (outcome_id,)
        ).fetchone()
        return Outcome.from_dict(json.loads(row["document"])) if row else None

    def list_outcomes(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT id, goal, status, created_at, updated_at FROM outcomes "
            "ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    # -- events ----------------------------------------------------------

    def append_events(self, outcome_id: str, events: Iterable[dict[str, Any]]) -> None:
        row = self._db.execute(
            "SELECT COALESCE(MAX(seq), -1) AS top FROM events WHERE outcome_id = ?",
            (outcome_id,),
        ).fetchone()
        seq = int(row["top"]) + 1
        for event in events:
            self._db.execute(
                "INSERT OR IGNORE INTO events (outcome_id, seq, at, kind, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (outcome_id, seq, event.get("at") or utc_now(), event["kind"], json.dumps(event)),
            )
            seq += 1
        self._db.commit()

    def events_for(self, outcome_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT payload FROM events WHERE outcome_id = ? ORDER BY seq", (outcome_id,)
        ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    # -- the call ledger -------------------------------------------------

    def find_call(self, idempotency_key: str) -> LedgerEntry | None:
        row = self._db.execute(
            "SELECT * FROM calls WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if row is None:
            return None
        return LedgerEntry(
            idempotency_key=row["idempotency_key"],
            outcome_id=row["outcome_id"],
            action_id=row["action_id"],
            phone=row["phone"],
            status=row["status"],
            call_id=row["call_id"],
            result=json.loads(row["result"]) if row["result"] else None,
            claimed_at=row["claimed_at"],
            completed_at=row["completed_at"],
        )

    def claim_call(
        self, idempotency_key: str, outcome_id: str, action_id: str, phone: str
    ) -> bool:
        """Write-ahead: reserve the key *before* dialling.

        Returns False if the key is already taken, which means this call has been
        placed before and must not be placed again.
        """
        try:
            self._db.execute(
                "INSERT INTO calls (idempotency_key, outcome_id, action_id, phone, "
                "status, claimed_at) VALUES (?, ?, ?, ?, 'claimed', ?)",
                (idempotency_key, outcome_id, action_id, phone, utc_now()),
            )
        except sqlite3.IntegrityError:
            return False
        self._db.commit()
        return True

    def complete_call(self, idempotency_key: str, call: CallOutcome) -> None:
        self._db.execute(
            "UPDATE calls SET status = ?, call_id = ?, result = ?, completed_at = ? "
            "WHERE idempotency_key = ?",
            (
                call.status,
                call.call_id,
                json.dumps({"structured": call.structured, "raw": call.raw}),
                utc_now(),
                idempotency_key,
            ),
        )
        self._db.commit()

    def calls_for(self, outcome_id: str) -> list[LedgerEntry]:
        rows = self._db.execute(
            "SELECT idempotency_key FROM calls WHERE outcome_id = ? ORDER BY claimed_at",
            (outcome_id,),
        ).fetchall()
        entries = [self.find_call(row["idempotency_key"]) for row in rows]
        return [e for e in entries if e is not None]

    def resolve_call(self, idempotency_key: str) -> bool:
        """Record that a human checked an unfinished call and it did happen.

        The stored result carries no evidence, because there is none: nobody
        knows what was said.

        It is recorded as `blocked` rather than `no_answer`, and the difference
        matters. `no_answer` is retryable — the planner would ring that number
        again, which is exactly the wrong move towards somebody who may have
        just spent five minutes on the phone with the agent. `blocked` means
        "we called, nothing came of it, move on": the credit is spent, the
        frontier advances, and nobody gets rung twice for one crash. An operator
        who knows the call never connected has `forget_call` instead.
        """
        entry = self.find_call(idempotency_key)
        if entry is None or entry.finished:
            return False
        # Recorded as 'completed' because the evidence extractor refuses to read
        # a structured block off a call the provider did not complete — and here
        # the operator, not the provider, is the authority on whether it
        # happened. Leaving it 'failed' would silently downgrade the verdict
        # below to no_answer, and no_answer is retryable.
        self._db.execute(
            "UPDATE calls SET status = 'completed', result = ?, completed_at = ? "
            "WHERE idempotency_key = ?",
            (
                json.dumps(
                    {
                        "structured": {
                            "reached": True,
                            "verdict": "blocked",
                            "facts": [],
                            "blockers": [
                                "This call was interrupted and its result was never "
                                "recorded. A human confirmed it was placed, so it is "
                                "not retried."
                            ],
                            "referrals": [],
                            "offer": None,
                        },
                        "raw": {"resolved_by_human": True},
                    }
                ),
                utc_now(),
                idempotency_key,
            ),
        )
        self._db.commit()
        return True

    def forget_call(self, idempotency_key: str) -> bool:
        """Record that a human checked and the call never happened.

        Deletes the claim so the number can be dialled. Only correct when the
        operator has actually established that no call was placed — otherwise
        this is the button that rings somebody twice.
        """
        cursor = self._db.execute(
            "DELETE FROM calls WHERE idempotency_key = ? AND result IS NULL",
            (idempotency_key,),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def unfinished_calls(self) -> list[LedgerEntry]:
        """Calls that were claimed and never completed — the ones a human should
        look at before anything is dialled again."""
        rows = self._db.execute(
            "SELECT idempotency_key FROM calls WHERE result IS NULL ORDER BY claimed_at"
        ).fetchall()
        entries = [self.find_call(row["idempotency_key"]) for row in rows]
        return [e for e in entries if e is not None]

    def all_calls(self) -> list[LedgerEntry]:
        """Every call the ledger has ever recorded, oldest first.

        The ledger is the only record of what was dialled — CALL-E has no
        endpoint that lists calls, so an id that is not here cannot be looked up
        anywhere. That makes reading it back an operator need in its own right,
        not just crash recovery.
        """
        rows = self._db.execute(
            "SELECT idempotency_key FROM calls ORDER BY claimed_at"
        ).fetchall()
        entries = [self.find_call(row["idempotency_key"]) for row in rows]
        return [e for e in entries if e is not None]
