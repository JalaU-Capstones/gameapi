"""Process-local cache of which users are currently in an active game.

This is a CACHE, not a source of truth. The DB (`gameplays` with
`invitation_state = 'accepted'` and `match_result IS NULL`) is authoritative.
On cold start or after a worker restart the cache is empty; callers must fall
back to a DB query when deciding whether a user is busy (see the `create_game`
handler in `api/v2/ws/gameplays.py`).

On multi-worker deployments, replace this module with a shared backend
(Redis) so all workers see a consistent view.
"""

from __future__ import annotations

from collections.abc import Iterable

from gameapi.api.v2.ws.manager import presence_manager

_playing_users: set[str] = set()


def reset_player_status() -> None:
    """Clear the in-memory ``playing`` cache. TEST-ONLY."""
    _playing_users.clear()


def is_playing(user_id: str) -> bool:
    return user_id in _playing_users


def playing_user_ids() -> list[str]:
    return [user_id for user_id in _playing_users if presence_manager.is_online(user_id)]


async def set_players_status(user_ids: Iterable[str | None], *, playing: bool) -> None:
    """Update the cache and broadcast a single status event per user."""
    user_id_set = {str(uid) for uid in user_ids if uid}
    if not user_id_set:
        return

    for user_id in sorted(user_id_set):
        if playing:
            _playing_users.add(user_id)
        elif user_id not in _playing_users:
            continue
        else:
            _playing_users.discard(user_id)

        await presence_manager.broadcast(
            {
                "event": "user_status",
                "payload": {"user_id": user_id, "status": "playing" if playing else "available"},
            }
        )
