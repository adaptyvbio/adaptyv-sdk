"""Common helper functions and base classes shared across workflow adapters.

These functions handle status normalization, error payloads, and state merging
for Modal volume-based streaming workflows.

Base classes:
- BaseDesign: Common design dataclass with serialization
- BaseWorkflowRun: Generic base class for workflow runs with Modal volume streaming
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast

if TYPE_CHECKING:
    pass

logger = logging.getLogger("adaptyv")


class WorkflowStatus(str, Enum):
    """Workflow run status.

    Used across all workflow adapters for consistent status reporting.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DesignStatus(str, Enum):
    """Individual design status within a workflow run."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


def normalize_error_payload(raw: Any) -> dict[str, Any] | None:
    """Normalize error payload to a consistent dict format.

    Args:
        raw: Raw error data (dict, string, or None)

    Returns:
        Normalized error dict with code, message, stage keys, or None
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        code = str(raw.get("code") or "unknown")
        message = str(raw.get("message") or "Workflow failed")
        stage = str(raw.get("stage") or "unknown")
        payload: dict[str, Any] = {"code": code, "message": message, "stage": stage}
        retryable = raw.get("retryable")
        if isinstance(retryable, bool):
            payload["retryable"] = retryable
        return payload
    message = str(raw).strip()
    if not message:
        message = "Workflow failed"
    return {"code": "unknown", "message": message, "stage": "unknown"}


def normalize_resume_hint(raw: Any) -> dict[str, Any] | None:
    """Normalize resume hint payload to a consistent dict format.

    Args:
        raw: Raw resume hint data (dict, string, or None)

    Returns:
        Normalized resume hint dict with stage, message keys, or None
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        stage = str(raw.get("stage") or "unknown")
        message = str(raw.get("message") or "Resume available")
        payload: dict[str, Any] = {"stage": stage, "message": message}
        retryable = raw.get("retryable")
        if isinstance(retryable, bool):
            payload["retryable"] = retryable
        return payload
    message = str(raw).strip()
    if not message:
        return None
    return {"stage": "unknown", "message": message}


def derive_status_from_state(state_data: dict[str, Any] | None) -> str:
    """Derive workflow status from state data.

    Args:
        state_data: State dict from state.json, or None

    Returns:
        Status string: "pending", "running", "completed", or "failed"
    """
    if not state_data:
        return WorkflowStatus.PENDING.value
    if state_data.get("error"):
        return WorkflowStatus.FAILED.value
    phase = state_data.get("phase")
    if phase == WorkflowStatus.FAILED.value:
        return WorkflowStatus.FAILED.value
    if phase == WorkflowStatus.COMPLETED.value:
        return WorkflowStatus.COMPLETED.value
    if phase:
        return WorkflowStatus.RUNNING.value
    return WorkflowStatus.PENDING.value


def merge_status_state(
    run_id: str,
    status_data: dict[str, Any] | None,
    state_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge status.json and state.json into a unified status payload.

    Combines data from both files, normalizes error and resume_hint fields,
    and ensures consistent status derivation.

    Args:
        run_id: The run identifier
        status_data: Data from status.json, or None
        state_data: Data from state.json, or None

    Returns:
        Merged status dict with run_id, status, phase, error, resume_hint
    """
    payload = dict(status_data) if status_data else {}
    payload.setdefault("run_id", run_id)
    if not payload.get("status"):
        payload["status"] = derive_status_from_state(state_data)
    if "phase" not in payload and state_data and state_data.get("phase"):
        payload["phase"] = state_data.get("phase")

    error = normalize_error_payload(payload.get("error"))
    if error is None and state_data:
        error = normalize_error_payload(state_data.get("error"))
    if payload.get("status") == WorkflowStatus.FAILED.value and error is None:
        error = normalize_error_payload("Workflow failed")
    if error is not None:
        payload["error"] = error
    else:
        payload.pop("error", None)

    if error is not None and payload.get("status") not in (
        WorkflowStatus.FAILED.value,
        WorkflowStatus.COMPLETED.value,
    ):
        payload["status"] = WorkflowStatus.FAILED.value

    resume_hint = normalize_resume_hint(payload.get("resume_hint"))
    if resume_hint is None and state_data:
        resume_hint = normalize_resume_hint(state_data.get("resume_hint"))
    if resume_hint is not None:
        payload["resume_hint"] = resume_hint
    else:
        payload.pop("resume_hint", None)

    # Include jobs progress from state.json for stage tracking
    if state_data and state_data.get("jobs"):
        payload["jobs"] = state_data["jobs"]
    if state_data and state_data.get("progress"):
        payload["progress"] = state_data["progress"]

    return payload


def read_json_from_volume(
    vol: Any,
    path: str,
    *,
    label: str,
) -> dict[str, Any] | None:
    """Read and parse JSON from a Modal volume.

    Args:
        vol: Modal Volume object
        path: Path to JSON file on the volume
        label: Label for logging (e.g., "status.json")

    Returns:
        Parsed dict, or None if file doesn't exist or is invalid
    """
    try:
        data = b"".join(vol.read_file(path))
        if not data:
            return None
        text = data.decode("utf-8")
        if not text.strip():
            return None
        payload = json.loads(text)
        if not isinstance(payload, dict):
            return None
        return payload
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
        logger.debug(f"Ignoring invalid {label} payload: {e}")
        return None


# --- Base Classes for Workflow Designs and Runs ---

D = TypeVar("D", bound="BaseDesign")


@dataclass
class BaseDesign:
    """Base design dataclass with common fields and serialization.

    Subclasses can add extra fields and override to_dict/from_dict.
    """

    design_id: str
    sequence: str
    structure_path: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    status: str = DesignStatus.PENDING.value

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict. Subclasses can extend with super().to_dict()."""
        return {
            "design_id": self.design_id,
            "sequence": self.sequence,
            "structure_path": self.structure_path,
            "metrics": self.metrics,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseDesign:
        """Create from dict. Subclasses should override for extra fields."""
        return cls(
            design_id=data.get("design_id", ""),
            sequence=data.get("sequence", ""),
            structure_path=data.get("structure_path"),
            metrics=data.get("metrics", {}),
            status=data.get("status", DesignStatus.PENDING.value),
        )


@dataclass
class BaseWorkflowRun(Generic[D]):
    """Base class for Modal volume streaming workflow runs.

    Provides common methods for:
    - Volume access (_get_volume, _volume_path)
    - Status retrieval (get_status)
    - Design listing (get_designs)
    - Streaming iteration (iter_designs)

    Subclasses must define:
    - design_class: ClassVar pointing to the design dataclass
    - output_volume: str with the Modal volume name (can have default)

    Example:
        @dataclass
        class MyRun(BaseWorkflowRun[MyDesign]):
            design_class = MyDesign
            output_volume: str = "my-volume"
    """

    run_id: str
    output_volume: str
    output_path: str | None = None
    _volume: Any = field(default=None, init=False, repr=False)

    # Subclasses must set this as a ClassVar
    design_class: ClassVar[type[BaseDesign]]
    default_poll_interval: ClassVar[float] = 10.0

    def _get_volume(self) -> Any:
        """Get cached Modal volume handle (avoids repeated network calls)."""
        if self._volume is None:
            import modal

            self._volume = modal.Volume.from_name(self.output_volume)
        return self._volume

    def _volume_path(self, path: str) -> str:
        """Convert container path to volume path.

        The volume is mounted at /output in the container, so /output/{run_id}
        becomes /{run_id} on the volume itself.
        """
        if path.startswith("/output"):
            return path[len("/output") :]
        return path

    def get_status(self) -> dict[str, Any]:
        """Get current run status from the volume.

        Returns:
            Status dict with keys: run_id, status, phase, error, etc.
            Returns {"status": "failed"} if status.json can't be read.
        """
        vol = self._get_volume()
        status_path = self._volume_path(f"{self.output_path}/status.json")
        state_path = self._volume_path(f"{self.output_path}/state.json")

        try:
            status_data = read_json_from_volume(vol, status_path, label="status.json")
            state_data = read_json_from_volume(vol, state_path, label="state.json")
        except Exception as e:
            logger.exception(f"Failed to read status for run {self.run_id}: {e}")
            return {
                "run_id": self.run_id,
                "status": WorkflowStatus.FAILED.value,
                "error": {
                    "code": "sdk_status_failed",
                    "message": "Failed to read workflow status.",
                    "stage": "status",
                    "retryable": True,
                },
            }

        return merge_status_state(self.run_id, status_data, state_data)

    def get_designs(self) -> list[D]:
        """Get all completed designs so far.

        Returns:
            List of design objects. Empty list if no designs yet.
        """
        vol = self._get_volume()
        designs_path = self._volume_path(f"{self.output_path}/designs")

        designs: list[D] = []
        try:
            for entry in vol.listdir(designs_path):
                # listdir returns FileEntry objects with .path as full path from volume root
                design_dir = entry.path if hasattr(entry, "path") else str(entry)
                design_json = f"/{design_dir}/design.json"
                try:
                    file_data = b"".join(vol.read_file(design_json))
                    data = json.loads(file_data.decode("utf-8"))
                    designs.append(cast(D, self.design_class.from_dict(data)))
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    # Skip incomplete designs (still being written)
                    logger.debug(f"Skipping incomplete design {design_json}: {e}")
                    continue
                except Exception as e:
                    # Handle any other read errors gracefully
                    logger.debug(f"Skipping design {design_json} due to error: {e}")
                    continue
        except (FileNotFoundError, Exception) as e:
            # designs/ directory doesn't exist yet, or other error
            if "NOT_FOUND" not in str(e) and "FileNotFoundError" not in str(type(e)):
                logger.debug(f"Error listing designs: {e}")

        return designs

    def iter_designs(self, poll_interval: float | None = None) -> Iterator[D]:
        """Iterate over designs as they're generated (streaming).

        Polls the Modal volume for new designs until run completes.

        Args:
            poll_interval: Seconds between polls. Defaults to class default_poll_interval.

        Yields:
            Design objects as they become available.
        """
        if poll_interval is None:
            poll_interval = self.default_poll_interval

        seen: set[str] = set()
        while True:
            status = self.get_status()

            for design in self.get_designs():
                if design.design_id not in seen:
                    seen.add(design.design_id)
                    yield design

            if status.get("status") == WorkflowStatus.COMPLETED.value:
                break

            if status.get("status") == WorkflowStatus.FAILED.value:
                error = status.get("error")
                message = error.get("message") if isinstance(error, dict) else error
                logger.warning(f"Run {self.run_id} failed: {message or 'Unknown error'}")
                break

            time.sleep(poll_interval)
