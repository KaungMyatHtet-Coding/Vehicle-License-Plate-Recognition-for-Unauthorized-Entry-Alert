"""Bounded, camera-free state for the local webcam demonstration."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Any


@dataclass(frozen=True)
class TrackObservation:
    """One selected Phase 4 result associated with a source-frame rectangle."""

    bbox: tuple[int, int, int, int]
    normalized_text: str | None
    reliable: bool
    confidence: float
    timestamp: float
    analysis: Any
    frame_bytes: bytes = b""
    correlation_id: str = ""


@dataclass
class _Track:
    track_id: int
    last_seen: float
    observations: deque[TrackObservation]


@dataclass(frozen=True)
class ConsensusResult:
    """Safe display/persistence decision for one bounded track update."""

    status: str
    normalized_text: str | None
    observation: TrackObservation | None
    track_id: int | None


def clip_bbox(
    bbox: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int] | None:
    """Clip an original-frame box and reject non-finite or zero-area geometry."""

    if width <= 0 or height <= 0 or len(bbox) != 4:
        return None
    if any(type(value) is not int for value in bbox):
        return None
    x1, y1, x2, y2 = bbox
    clipped = (
        max(0, min(x1, width)),
        max(0, min(y1, height)),
        max(0, min(x2, width)),
        max(0, min(y2, height)),
    )
    return clipped if clipped[2] > clipped[0] and clipped[3] > clipped[1] else None


def intersection_over_union(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> float:
    """Return a finite IoU for two validated or unvalidated rectangles."""

    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0, min(ay2, by2) - max(ay1, by1)
    )
    first_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    second_area = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


class TemporalConsensus:
    """Associate observations by space and require exact repeated OCR."""

    def __init__(
        self,
        *,
        required_agreements: int = 2,
        observation_window: int = 4,
        track_expiry_seconds: float = 2.0,
        max_tracks: int = 8,
        iou_threshold: float = 0.30,
    ) -> None:
        if required_agreements < 2 or observation_window < required_agreements:
            raise ValueError("consensus bounds are inconsistent")
        if track_expiry_seconds <= 0 or max_tracks < 1:
            raise ValueError("consensus bounds must be positive")
        if not math.isfinite(iou_threshold) or not 0.0 <= iou_threshold <= 1.0:
            raise ValueError("IoU threshold must be between zero and one")
        self.required_agreements = required_agreements
        self.observation_window = observation_window
        self.track_expiry_seconds = track_expiry_seconds
        self.max_tracks = max_tracks
        self.iou_threshold = iou_threshold
        self._tracks: dict[int, _Track] = {}
        self._next_track_id = 1

    @property
    def track_count(self) -> int:
        return len(self._tracks)

    def update(self, observation: TrackObservation) -> ConsensusResult:
        """Add one observation, returning stable output only after exact agreement."""

        self._expire(observation.timestamp)
        track = self._match(observation.bbox)
        if track is None:
            if len(self._tracks) >= self.max_tracks:
                oldest = min(
                    self._tracks.values(),
                    key=lambda item: (item.last_seen, item.track_id),
                )
                self._remove_track(oldest.track_id)
            track = _Track(
                self._next_track_id,
                observation.timestamp,
                deque(maxlen=self.observation_window),
            )
            self._next_track_id += 1
            self._tracks[track.track_id] = track
        track.last_seen = observation.timestamp
        track.observations.append(observation)

        reliable = [
            item
            for item in track.observations
            if item.reliable and item.normalized_text
        ]
        counts: dict[str, int] = {}
        for item in reliable:
            assert item.normalized_text is not None
            counts[item.normalized_text] = counts.get(item.normalized_text, 0) + 1
        if len(counts) > 1:
            return ConsensusResult("MANUAL_REVIEW", None, None, track.track_id)
        winners = [
            text for text, count in counts.items() if count >= self.required_agreements
        ]
        if len(winners) != 1:
            return ConsensusResult("MANUAL_REVIEW", None, None, track.track_id)
        text = winners[0]
        best = max(
            (item for item in reliable if item.normalized_text == text),
            key=lambda item: (item.confidence, item.timestamp, item.bbox),
        )
        return ConsensusResult("stable", text, best, track.track_id)

    def _match(self, bbox: tuple[int, int, int, int]) -> _Track | None:
        matches = [
            (intersection_over_union(bbox, track.observations[-1].bbox), track)
            for track in self._tracks.values()
            if track.observations
        ]
        matches = [item for item in matches if item[0] >= self.iou_threshold]
        if not matches:
            return None
        return max(matches, key=lambda item: (item[0], -item[1].track_id))[1]

    def _expire(self, now: float) -> None:
        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if now - track.last_seen >= self.track_expiry_seconds
        ]
        for track_id in expired:
            self._remove_track(track_id)

    def _remove_track(self, track_id: int) -> None:
        track = self._tracks.pop(track_id, None)
        if track is not None:
            track.observations.clear()


class CooldownLedger:
    """Bounded pre-persistence duplicate suppression state."""

    def __init__(self, cooldown_seconds: float, max_entries: int = 64) -> None:
        if cooldown_seconds <= 0 or max_entries < 1:
            raise ValueError("cooldown bounds must be positive")
        self.cooldown_seconds = cooldown_seconds
        self.max_entries = max_entries
        self._last_seen: dict[str, float] = {}

    @property
    def size(self) -> int:
        return len(self._last_seen)

    def is_suppressed(self, normalized_text: str, timestamp: float) -> bool:
        """Check cooldown state without recording a new event."""

        self._expire(timestamp)
        previous = self._last_seen.get(normalized_text)
        return previous is not None and timestamp - previous < self.cooldown_seconds

    def record(self, normalized_text: str, timestamp: float) -> None:
        """Record a successfully persisted event in the bounded cooldown ledger."""

        self._expire(timestamp)
        if (
            normalized_text not in self._last_seen
            and len(self._last_seen) >= self.max_entries
        ):
            oldest = min(self._last_seen, key=lambda key: (self._last_seen[key], key))
            del self._last_seen[oldest]
        self._last_seen[normalized_text] = timestamp
        return False

    def _expire(self, now: float) -> None:
        for text in [
            text
            for text, timestamp in self._last_seen.items()
            if now - timestamp >= self.cooldown_seconds
        ]:
            del self._last_seen[text]
