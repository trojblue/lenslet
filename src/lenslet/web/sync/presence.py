from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class PresenceCount:
    gallery_id: str
    viewing: int
    editing: int


@dataclass
class _PresenceSession:
    gallery_id: str
    lease_id: str
    last_view: float
    last_edit: float = 0.0


class PresenceLeaseError(Exception):
    pass


class PresenceMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._invalid_lease_total = 0

    def record_invalid_lease(self) -> None:
        with self._lock:
            self._invalid_lease_total += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"invalid_lease_total": self._invalid_lease_total}


class PresenceScopeError(Exception):
    def __init__(self, expected_gallery_id: str, actual_gallery_id: str) -> None:
        super().__init__(f"scope mismatch: expected={expected_gallery_id}, actual={actual_gallery_id}")
        self.expected_gallery_id = expected_gallery_id
        self.actual_gallery_id = actual_gallery_id


class PresenceTracker:
    def __init__(self, view_ttl: float = 75.0, edit_ttl: float = 60.0) -> None:
        self._view_ttl = view_ttl
        self._edit_ttl = edit_ttl
        self._lock = threading.Lock()
        self._sessions: dict[str, _PresenceSession] = {}
        self._clients_by_scope: dict[str, set[str]] = {}
        self._stale_pruned_total = 0

    @property
    def view_ttl_seconds(self) -> float:
        return self._view_ttl

    @property
    def edit_ttl_seconds(self) -> float:
        return self._edit_ttl

    def _new_lease(self) -> str:
        return uuid4().hex

    def _scope_add_locked(self, gallery_id: str, client_id: str) -> None:
        members = self._clients_by_scope.setdefault(gallery_id, set())
        members.add(client_id)

    def _scope_remove_locked(self, gallery_id: str, client_id: str) -> None:
        members = self._clients_by_scope.get(gallery_id)
        if members is None:
            return
        members.discard(client_id)
        if not members:
            self._clients_by_scope.pop(gallery_id, None)

    def _remove_client_locked(self, client_id: str) -> str | None:
        session = self._sessions.pop(client_id, None)
        if session is None:
            return None
        self._scope_remove_locked(session.gallery_id, client_id)
        return session.gallery_id

    def _is_viewing(self, session: _PresenceSession, now: float) -> bool:
        return (now - session.last_view) <= self._view_ttl

    def _is_editing(self, session: _PresenceSession, now: float) -> bool:
        if session.last_edit <= 0.0:
            return False
        return (now - session.last_edit) <= self._edit_ttl

    def _prune_stale_locked(self, now: float) -> set[str]:
        affected: set[str] = set()
        if not self._sessions:
            return affected
        stale_clients: list[str] = []
        for client_id, session in self._sessions.items():
            if self._is_viewing(session, now) or self._is_editing(session, now):
                continue
            stale_clients.append(client_id)
        for client_id in stale_clients:
            removed_scope = self._remove_client_locked(client_id)
            if removed_scope is not None:
                self._stale_pruned_total += 1
                affected.add(removed_scope)
        return affected

    def _counts_locked(self, gallery_id: str, now: float) -> tuple[int, int]:
        members = self._clients_by_scope.get(gallery_id)
        if not members:
            return 0, 0
        viewing = 0
        editing = 0
        for client_id in tuple(members):
            session = self._sessions.get(client_id)
            if session is None or session.gallery_id != gallery_id:
                self._scope_remove_locked(gallery_id, client_id)
                continue
            if self._is_viewing(session, now):
                viewing += 1
            if self._is_editing(session, now):
                editing += 1
        return viewing, editing

    def _counts_payloads_locked(self, scopes: set[str], now: float) -> list[PresenceCount]:
        payloads: list[PresenceCount] = []
        for gallery_id in sorted(scopes):
            viewing, editing = self._counts_locked(gallery_id, now)
            payloads.append(PresenceCount(gallery_id=gallery_id, viewing=viewing, editing=editing))
        return payloads

    def _session_for_lease_locked(self, client_id: str, lease_id: str) -> _PresenceSession:
        session = self._sessions.get(client_id)
        if session is None or session.lease_id != lease_id:
            raise PresenceLeaseError("invalid lease")
        return session

    def _resolve_session_locked(
        self,
        gallery_id: str,
        client_id: str,
        now: float,
        lease_id: str | None = None,
    ) -> tuple[str, set[str]]:
        affected: set[str] = {gallery_id}
        session = self._sessions.get(client_id)
        if session is None:
            lease = self._new_lease()
            self._sessions[client_id] = _PresenceSession(
                gallery_id=gallery_id,
                lease_id=lease,
                last_view=now,
                last_edit=0.0,
            )
            self._scope_add_locked(gallery_id, client_id)
            return lease, affected

        if lease_id and session.lease_id != lease_id:
            raise PresenceLeaseError("invalid lease")

        lease = session.lease_id
        if session.gallery_id != gallery_id:
            old_gallery = session.gallery_id
            self._scope_remove_locked(old_gallery, client_id)
            session.gallery_id = gallery_id
            session.last_edit = 0.0
            self._scope_add_locked(gallery_id, client_id)
            affected.add(old_gallery)
        session.last_view = now
        return lease, affected

    def _touch_locked(
        self,
        gallery_id: str,
        client_id: str,
        now: float,
        lease_id: str | None = None,
        *,
        editing: bool,
    ) -> tuple[str, list[PresenceCount]]:
        affected = self._prune_stale_locked(now)
        lease, touched = self._resolve_session_locked(gallery_id, client_id, now, lease_id=lease_id)
        if editing:
            self._sessions[client_id].last_edit = now
        affected.update(touched)
        return lease, self._counts_payloads_locked(affected, now)

    def join(self, gallery_id: str, client_id: str, lease_id: str | None = None) -> tuple[str, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            affected = self._prune_stale_locked(now)
            existing = self._sessions.get(client_id)
            reuse_existing_lease = existing is not None and lease_id == existing.lease_id
            if existing is not None and lease_id and not reuse_existing_lease:
                raise PresenceLeaseError("invalid lease")
            if existing is not None and not reuse_existing_lease:
                removed_scope = self._remove_client_locked(client_id)
                if removed_scope is not None:
                    affected.add(removed_scope)
            resolved_lease = lease_id if reuse_existing_lease else None
            lease, touched = self._resolve_session_locked(gallery_id, client_id, now, lease_id=resolved_lease)
            affected.update(touched)
            return lease, self._counts_payloads_locked(affected, now)

    def touch_view(
        self,
        gallery_id: str,
        client_id: str,
        lease_id: str | None = None,
    ) -> tuple[str, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            return self._touch_locked(gallery_id, client_id, now, lease_id=lease_id, editing=False)

    def touch_edit(
        self,
        gallery_id: str,
        client_id: str,
        lease_id: str | None = None,
    ) -> tuple[str, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            return self._touch_locked(gallery_id, client_id, now, lease_id=lease_id, editing=True)

    def move(
        self,
        from_gallery_id: str,
        to_gallery_id: str,
        client_id: str,
        lease_id: str,
    ) -> list[PresenceCount]:
        now = time.monotonic()
        with self._lock:
            affected = self._prune_stale_locked(now)
            session = self._session_for_lease_locked(client_id, lease_id)
            current = session.gallery_id
            if current == to_gallery_id:
                session.last_view = now
                affected.add(current)
                return self._counts_payloads_locked(affected, now)
            if current != from_gallery_id:
                raise PresenceScopeError(expected_gallery_id=from_gallery_id, actual_gallery_id=current)
            self._scope_remove_locked(current, client_id)
            session.gallery_id = to_gallery_id
            session.last_view = now
            session.last_edit = 0.0
            self._scope_add_locked(to_gallery_id, client_id)
            affected.add(current)
            affected.add(to_gallery_id)
            return self._counts_payloads_locked(affected, now)

    def leave(
        self,
        gallery_id: str,
        client_id: str,
        lease_id: str,
    ) -> tuple[bool, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            affected = self._prune_stale_locked(now)
            affected.add(gallery_id)
            session = self._sessions.get(client_id)
            if session is None:
                return False, self._counts_payloads_locked(affected, now)
            if session.lease_id != lease_id:
                raise PresenceLeaseError("invalid lease")
            if session.gallery_id != gallery_id:
                raise PresenceScopeError(expected_gallery_id=gallery_id, actual_gallery_id=session.gallery_id)
            removed_scope = self._remove_client_locked(client_id)
            if removed_scope is not None:
                affected.add(removed_scope)
            return True, self._counts_payloads_locked(affected, now)

    def snapshot_counts(self) -> dict[str, PresenceCount]:
        now = time.monotonic()
        with self._lock:
            self._prune_stale_locked(now)
            out: dict[str, PresenceCount] = {}
            for gallery_id in sorted(self._clients_by_scope):
                viewing, editing = self._counts_locked(gallery_id, now)
                out[gallery_id] = PresenceCount(gallery_id=gallery_id, viewing=viewing, editing=editing)
            return out

    def debug_state(self) -> dict[str, Any]:
        with self._lock:
            clients = {
                client_id: {
                    "gallery_id": session.gallery_id,
                    "lease_id": session.lease_id,
                    "last_view": session.last_view,
                    "last_edit": session.last_edit,
                }
                for client_id, session in self._sessions.items()
            }
            scopes = {gallery_id: sorted(members) for gallery_id, members in self._clients_by_scope.items()}
            return {
                "clients": clients,
                "scopes": scopes,
                "stale_pruned_total": self._stale_pruned_total,
            }

    def diagnostics(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_clients": len(self._sessions),
                "active_scopes": len(self._clients_by_scope),
                "stale_pruned_total": self._stale_pruned_total,
            }
