"""Local SQLite storage for design runs, designs, and sessions.

This module provides a unified local storage layer for the protein designer agent,
replacing both the file-based SessionLogger and the Modal Dict-based RunRegistry.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path.home() / ".adaptyv" / "runs.db"


def _now_iso() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    """Convert a row to a dictionary using column names."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class LocalStorage:
    """SQLite-based local storage for runs, designs, and sessions.

    All data is stored in a single SQLite database at ~/.adaptyv/runs.db.
    This class is thread-safe and can be used from multiple processes.

    Usage:
        storage = LocalStorage()

        # Create a session and run
        session_id = storage.create_session()
        run = storage.create_run(model="design-a-protein", config={}, session_id=session_id)

        # Log conversation
        storage.log_message(session_id, "user", "Design a binder for CD20")
        storage.log_tool_call(session_id, "design_binder", {"target": "CD20"}, {"status": "success"})

        # Update run status
        storage.update_run(run["id"], status="completed", completed_designs=10)
    """

    def __init__(self, db_path: Path | str | None = None):
        """Initialize local storage.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.adaptyv/runs.db
        """
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    model TEXT NOT NULL,
                    name TEXT,
                    status TEXT DEFAULT 'pending',
                    config TEXT,
                    target_pdb_url TEXT,
                    target_id TEXT,
                    hotspots TEXT,
                    total_designs INTEGER DEFAULT 0,
                    completed_designs INTEGER DEFAULT 0,
                    error TEXT,
                    modal_job_id TEXT,
                    foundry_experiment_id TEXT,
                    proteinbase_collection_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS designs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    design_id TEXT NOT NULL,
                    sequence TEXT NOT NULL,
                    structure_path TEXT,
                    metrics TEXT,
                    review_status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, design_id),
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    agent_state TEXT,
                    agent_config TEXT,
                    context TEXT,
                    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    inputs TEXT,
                    outputs TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_runs_session_id ON runs(session_id);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_designs_run_id ON designs(run_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_run_id ON sessions(run_id);
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_tool_calls_session_id ON tool_calls(session_id);
            """)

    # --- Run methods ---

    def create_run(
        self,
        *,
        model: str,
        config: dict[str, Any] | None = None,
        name: str | None = None,
        session_id: str | None = None,
        target_pdb_url: str | None = None,
        target_id: str | None = None,
        hotspots: list[str] | None = None,
        id: str | None = None,
        modal_job_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new design run.

        Args:
            model: Model name (e.g., "design-a-protein", "bindcraft")
            config: Run configuration as dict
            name: Optional run name
            session_id: Link to session that created this run
            target_pdb_url: URL to target PDB file
            target_id: Foundry catalog target UUID (for experiment submission)
            hotspots: List of hotspot residues
            id: Optional custom run ID (e.g., from Modal). If not provided, generates 8-char hex.
            modal_job_id: Optional Modal job ID for tracking

        Returns:
            Created run as dict
        """
        run_id = id if id else uuid.uuid4().hex[:8]
        now = _now_iso()

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runs
                   (id, session_id, model, name, config, target_pdb_url, target_id, hotspots, modal_job_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    session_id,
                    model,
                    name,
                    json.dumps(config) if config else None,
                    target_pdb_url,
                    target_id,
                    json.dumps(hotspots) if hotspots else None,
                    modal_job_id,
                    now,
                    now,
                ),
            )

            # Link session to run if provided
            if session_id:
                conn.execute("UPDATE sessions SET run_id = ? WHERE id = ?", (run_id, session_id))

        return {
            "id": run_id,
            "session_id": session_id,
            "model": model,
            "name": name,
            "status": "pending",
            "config": config,
            "target_pdb_url": target_pdb_url,
            "target_id": target_id,
            "hotspots": hotspots,
            "modal_job_id": modal_job_id,
            "total_designs": 0,
            "completed_designs": 0,
            "created_at": now,
            "updated_at": now,
        }

    def update_run(self, run_id: str, **updates: Any) -> dict[str, Any] | None:
        """Update run fields.

        Args:
            run_id: Run ID to update
            **updates: Fields to update (status, error, modal_job_id, etc.)

        Returns:
            Updated run or None if not found
        """
        if not updates:
            return self.get_run(run_id)

        # Handle JSON fields
        json_fields = {"config", "hotspots"}
        for field in json_fields:
            if field in updates and updates[field] is not None:
                updates[field] = json.dumps(updates[field])

        updates["updated_at"] = _now_iso()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [run_id]

        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {set_clause} WHERE id = ?", values)

        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get run by ID.

        Args:
            run_id: Run ID (supports prefix matching)

        Returns:
            Run as dict or None if not found
        """
        with self._connect() as conn:
            # Support prefix matching
            cursor = conn.execute(
                "SELECT * FROM runs WHERE id = ? OR id LIKE ?",
                (run_id, f"{run_id}%"),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._parse_run_row(dict(row))

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        model: str | None = None,
    ) -> list[dict[str, Any]]:
        """List runs ordered by creation time (newest first).

        Args:
            limit: Max runs to return
            offset: Number of runs to skip
            status: Filter by status
            model: Filter by model

        Returns:
            List of runs
        """
        query = "SELECT * FROM runs WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if model:
            query += " AND model = ?"
            params.append(model)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [self._parse_run_row(dict(row)) for row in cursor.fetchall()]

    def _parse_run_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Parse JSON fields in a run row."""
        if row.get("config"):
            row["config"] = json.loads(row["config"])
        if row.get("hotspots"):
            row["hotspots"] = json.loads(row["hotspots"])
        return row

    # --- Design methods ---

    def add_design(
        self,
        run_id: str,
        *,
        design_id: str,
        sequence: str,
        structure_path: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a design to a run.

        Args:
            run_id: Parent run ID
            design_id: Design identifier within the run
            sequence: Protein sequence
            structure_path: Path to local PDB file
            metrics: Design metrics (plddt, ipae, etc.)

        Returns:
            Created design as dict
        """
        id_ = uuid.uuid4().hex[:12]
        now = _now_iso()

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO designs (id, run_id, design_id, sequence, structure_path, metrics, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(run_id, design_id) DO UPDATE SET
                   sequence = excluded.sequence,
                   structure_path = excluded.structure_path,
                   metrics = excluded.metrics""",
                (
                    id_,
                    run_id,
                    design_id,
                    sequence,
                    structure_path,
                    json.dumps(metrics) if metrics else None,
                    now,
                ),
            )

            # Update completed_designs count
            conn.execute(
                """UPDATE runs SET
                   completed_designs = (SELECT COUNT(*) FROM designs WHERE run_id = ?),
                   updated_at = ?
                   WHERE id = ?""",
                (run_id, now, run_id),
            )

        return {
            "id": id_,
            "run_id": run_id,
            "design_id": design_id,
            "sequence": sequence,
            "structure_path": structure_path,
            "metrics": metrics,
            "review_status": "pending",
            "created_at": now,
        }

    def update_design(self, run_id: str, design_id: str, **updates: Any) -> dict[str, Any] | None:
        """Update a design.

        Args:
            run_id: Run ID
            design_id: Design ID within run
            **updates: Fields to update (review_status, metrics, etc.)

        Returns:
            Updated design or None if not found
        """
        if "metrics" in updates and updates["metrics"] is not None:
            updates["metrics"] = json.dumps(updates["metrics"])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [run_id, design_id]

        with self._connect() as conn:
            conn.execute(
                f"UPDATE designs SET {set_clause} WHERE run_id = ? AND design_id = ?",
                values,
            )

        return self.get_design(run_id, design_id)

    def get_design(self, run_id: str, design_id: str) -> dict[str, Any] | None:
        """Get a specific design."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM designs WHERE run_id = ? AND design_id = ?",
                (run_id, design_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._parse_design_row(dict(row))

    def list_designs(
        self,
        run_id: str,
        *,
        review_status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List designs for a run.

        Args:
            run_id: Run ID
            review_status: Filter by review status (pending/approved/rejected)

        Returns:
            List of designs
        """
        query = "SELECT * FROM designs WHERE run_id = ?"
        params: list[Any] = [run_id]

        if review_status:
            query += " AND review_status = ?"
            params.append(review_status)

        query += " ORDER BY created_at"

        with self._connect() as conn:
            cursor = conn.execute(query, params)
            return [self._parse_design_row(dict(row)) for row in cursor.fetchall()]

    def _parse_design_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Parse JSON fields in a design row."""
        if row.get("metrics"):
            row["metrics"] = json.loads(row["metrics"])
        return row

    # --- Session methods ---

    def create_session(self, run_id: str | None = None) -> str:
        """Create a new session.

        Args:
            run_id: Optional run to link to

        Returns:
            Session ID
        """
        session_id = uuid.uuid4().hex[:8]
        now = _now_iso()

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, run_id, start_time) VALUES (?, ?, ?)",
                (session_id, run_id, now),
            )

        return session_id

    def link_session_to_run(self, session_id: str, run_id: str) -> None:
        """Link an existing session to a run.

        This is useful when a run is created mid-session.

        Args:
            session_id: Session ID
            run_id: Run ID
        """
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET run_id = ? WHERE id = ?", (run_id, session_id))
            conn.execute("UPDATE runs SET session_id = ? WHERE id = ?", (session_id, run_id))

    def update_session(self, session_id: str, **updates: Any) -> None:
        """Update session fields.

        Args:
            session_id: Session ID
            **updates: Fields to update (agent_state, agent_config, context, end_time)
        """
        # Handle JSON fields
        json_fields = {"agent_state", "agent_config", "context"}
        for field in json_fields:
            if field in updates and updates[field] is not None:
                updates[field] = json.dumps(updates[field])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [session_id]

        with self._connect() as conn:
            conn.execute(f"UPDATE sessions SET {set_clause} WHERE id = ?", values)

    def finalize_session(self, session_id: str) -> None:
        """Mark session as complete."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET end_time = ? WHERE id = ?",
                (_now_iso(), session_id),
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session by ID."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ? OR id LIKE ?",
                (session_id, f"{session_id}%"),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._parse_session_row(dict(row))

    def get_session_for_run(self, run_id: str) -> dict[str, Any] | None:
        """Get the session linked to a run."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._parse_session_row(dict(row))

    def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent sessions."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions ORDER BY start_time DESC LIMIT ?",
                (limit,),
            )
            return [self._parse_session_row(dict(row)) for row in cursor.fetchall()]

    def find_latest_session(self) -> dict[str, Any] | None:
        """Find the most recent session."""
        with self._connect() as conn:
            cursor = conn.execute("SELECT * FROM sessions ORDER BY start_time DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            return self._parse_session_row(dict(row))

    def _parse_session_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Parse JSON fields in a session row."""
        for field in ("agent_state", "agent_config", "context"):
            if row.get(field):
                row[field] = json.loads(row[field])
        return row

    # --- Message methods ---

    def log_message(
        self,
        session_id: str,
        role: str,
        content: str,
        **metadata: Any,
    ) -> None:
        """Log a message in session conversation history.

        Args:
            session_id: Session ID
            role: Message role (user/assistant/system)
            content: Message content
            **metadata: Additional metadata (tool_calls, name, etc.)
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO messages (session_id, ts, role, content, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session_id,
                    _now_iso(),
                    role,
                    content,
                    json.dumps(metadata) if metadata else None,
                ),
            )

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Get all messages for a session.

        Args:
            session_id: Session ID

        Returns:
            List of messages ordered by timestamp
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY ts",
                (session_id,),
            )
            messages = []
            for row in cursor.fetchall():
                msg = dict(row)
                if msg.get("metadata"):
                    msg["metadata"] = json.loads(msg["metadata"])
                messages.append(msg)
            return messages

    # --- Tool call methods ---

    def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
    ) -> None:
        """Log a tool invocation.

        Args:
            session_id: Session ID
            tool_name: Name of the tool called
            inputs: Tool input parameters
            outputs: Tool output/result
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tool_calls (session_id, ts, tool_name, inputs, outputs)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    session_id,
                    _now_iso(),
                    tool_name,
                    json.dumps(inputs),
                    json.dumps(outputs),
                ),
            )

    def list_tool_calls(self, session_id: str) -> list[dict[str, Any]]:
        """Get all tool calls for a session.

        Args:
            session_id: Session ID

        Returns:
            List of tool calls ordered by timestamp
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM tool_calls WHERE session_id = ? ORDER BY ts",
                (session_id,),
            )
            calls = []
            for row in cursor.fetchall():
                call = dict(row)
                if call.get("inputs"):
                    call["inputs"] = json.loads(call["inputs"])
                if call.get("outputs"):
                    call["outputs"] = json.loads(call["outputs"])
                calls.append(call)
            return calls

    # --- Aggregate methods ---

    def get_run_metrics(self, run_id: str) -> dict[str, Any]:
        """Get aggregated metrics for a run.

        Args:
            run_id: Run ID

        Returns:
            Aggregated metrics (mean ipTM, shape complementarity, counts, etc.)
        """
        designs = self.list_designs(run_id)
        if not designs:
            return {
                "total_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "pending_count": 0,
            }

        metrics_list = [d.get("metrics", {}) for d in designs if d.get("metrics")]

        def mean(key: str) -> float | None:
            values = [m.get(key) for m in metrics_list if m.get(key) is not None]
            return sum(values) / len(values) if values else None

        def max_val(key: str) -> float | None:
            values = [m.get(key) for m in metrics_list if m.get(key) is not None]
            return max(values) if values else None

        status_counts = {"approved": 0, "rejected": 0, "pending": 0}
        for d in designs:
            status = d.get("review_status", "pending")
            if status in status_counts:
                status_counts[status] += 1

        return {
            "total_count": len(designs),
            "approved_count": status_counts["approved"],
            "rejected_count": status_counts["rejected"],
            "pending_count": status_counts["pending"],
            "success_rate": status_counts["approved"] / len(designs) if designs else 0,
            "iptm_mean": mean("iptm"),
            "iptm_best": max_val("iptm"),
            "shape_complementarity_mean": mean("shape_complementarity"),
            "shape_complementarity_best": max_val("shape_complementarity"),
            "mpnn_score_mean": mean("mpnn_score"),
        }


__all__ = ["LocalStorage", "DEFAULT_DB_PATH"]
