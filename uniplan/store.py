"""Consent-only local storage for validated profiles, comparisons and outcomes.

Nothing is written unless the student ticked the consent box. One random
profile code withdraws every record linked to it.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CODE_RE = re.compile(r"^[0-9a-f]{32}$")
OUTCOME_EVENTS = {"study_completed", "accepted"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        connection = sqlite3.connect(self.path)
        os.chmod(self.path, 0o600)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                snapshot_json TEXT,
                consent_time TEXT NOT NULL
            )
        """)
        # One person may submit several scenarios; they share a participant code
        # (the first profile code), which also withdraws everything at once.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(profiles)")}
        if "participant_id" not in columns:
            connection.execute("ALTER TABLE profiles ADD COLUMN participant_id TEXT")
        # One row per answered comparison: the proposal's `choices` dataset.
        connection.execute("""
            CREATE TABLE IF NOT EXISTS choices (
                profile_id TEXT NOT NULL,
                study_id TEXT NOT NULL,
                study_seed INTEGER NOT NULL,
                pair_index INTEGER NOT NULL,
                split TEXT NOT NULL CHECK (split IN ('train', 'test')),
                candidate_a TEXT NOT NULL,
                candidate_b TEXT NOT NULL,
                x_a TEXT NOT NULL,
                x_b TEXT NOT NULL,
                choice TEXT NOT NULL CHECK (choice IN ('A', 'B', 'tie')),
                baseline_weights TEXT NOT NULL,
                fit_scale TEXT NOT NULL,
                created_time TEXT NOT NULL,
                PRIMARY KEY (study_id, pair_index)
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                profile_id TEXT NOT NULL,
                event TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                elapsed_ms INTEGER,
                created_time TEXT NOT NULL
            )
        """)
        return connection

    def save(self, profile: dict[str, Any], snapshot_ref: dict[str, Any] | None,
             participant: str | None = None) -> str:
        """Store a consented profile; return the participant code to show the student.

        A known ``participant`` code links this profile to that person's
        earlier ones; anything else starts a new participant.
        """
        code = profile["profile_id"]
        if not CODE_RE.fullmatch(code):
            raise ValueError("Invalid profile code")
        with self._connect() as connection:
            known = (participant is not None and CODE_RE.fullmatch(participant) is not None and
                     connection.execute("SELECT 1 FROM profiles WHERE participant_id = ? OR profile_id = ?",
                                        (participant, participant)).fetchone() is not None)
            participant_id = participant if known else code
            connection.execute(
                "INSERT INTO profiles (profile_id, profile_json, snapshot_json, consent_time, participant_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (code, json.dumps(profile, ensure_ascii=False),
                 json.dumps(snapshot_ref, ensure_ascii=False), _now(), participant_id),
            )
        return participant_id

    def has_profile(self, code: str) -> bool:
        if not CODE_RE.fullmatch(code) or not self.path.exists():
            return False
        with self._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM profiles WHERE profile_id = ?", (code,)).fetchone() is not None

    def save_choices(self, profile_id: str, study_id: str, seed: int,
                     baseline_weights: dict[str, float], rows: list[dict[str, Any]],
                     fit_scale: list[float]) -> None:
        """Replace this study's answers; resubmitting a study overwrites, never duplicates.

        ``fit_scale`` is the per-feature spread the app divided by, so the
        evaluation script can refit exactly the model the student saw.
        """
        if not CODE_RE.fullmatch(profile_id) or not CODE_RE.fullmatch(study_id):
            raise ValueError("Invalid code")
        created = _now()
        with self._connect() as connection:
            connection.execute("DELETE FROM choices WHERE study_id = ?", (study_id,))
            connection.executemany(
                "INSERT INTO choices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(profile_id, study_id, seed, row["pair_index"], row["split"],
                  row["candidate_a"], row["candidate_b"], json.dumps(row["x_a"]),
                  json.dumps(row["x_b"]), row["choice"], json.dumps(baseline_weights),
                  json.dumps(fit_scale), created)
                 for row in rows],
            )

    def record_outcome(self, profile_id: str, event: str, detail: dict[str, Any],
                       elapsed_ms: int | None) -> bool:
        """Store a timing/acceptance event for a consented profile only."""
        if event not in OUTCOME_EVENTS or not self.has_profile(profile_id):
            return False
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO outcomes VALUES (?, ?, ?, ?, ?)",
                (profile_id, event, json.dumps(detail, ensure_ascii=False), elapsed_ms, _now()),
            )
        return True

    def load_choices(self) -> list[dict[str, Any]]:
        """All consented comparisons, for offline evaluation scripts."""
        if not self.path.exists():
            return []
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT choices.*, COALESCE(profiles.participant_id, choices.profile_id) AS participant_id "
                "FROM choices LEFT JOIN profiles USING (profile_id) "
                "ORDER BY study_id, pair_index").fetchall()
        return [{**dict(row), "x_a": json.loads(row["x_a"]), "x_b": json.loads(row["x_b"]),
                 "baseline_weights": json.loads(row["baseline_weights"]),
                 "fit_scale": json.loads(row["fit_scale"])} for row in rows]

    def load_outcomes(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT outcomes.*, COALESCE(profiles.participant_id, outcomes.profile_id) AS participant_id "
                "FROM outcomes LEFT JOIN profiles USING (profile_id) "
                "ORDER BY created_time, outcomes.rowid").fetchall()
        return [{**dict(row), "detail": json.loads(row["detail_json"])} for row in rows]

    def withdraw(self, code: str) -> bool:
        """Delete everything linked to a profile or participant code."""
        if not CODE_RE.fullmatch(code) or not self.path.exists():
            return False
        with self._connect() as connection:
            linked = [row[0] for row in connection.execute(
                "SELECT profile_id FROM profiles WHERE profile_id = ? OR participant_id = ?", (code, code))]
            linked = linked or [code]
            removed = 0
            for profile_id in linked:
                for table in ("choices", "outcomes", "profiles"):
                    removed += connection.execute(
                        f"DELETE FROM {table} WHERE profile_id = ?", (profile_id,)).rowcount
            return removed > 0
