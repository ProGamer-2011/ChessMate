import json
import os
from typing import Any

import requests

from player_profile.profile_manager import load_profile, save_profile

BASE_URL = "https://api.chess.com/pub/player"

HEADERS = {
    "User-Agent": "ChessMate/1.0 (educational project)"
}

SYNC_IDS_KEY = "chesscom_synced_game_urls"
SYNC_COUNT_KEY = "chesscom_synced_game_count"
LAST_SYNC_KEY = "last_chesscom_sync"


# -------------------------
# PROFILE HELPERS
# -------------------------

def _load_profile_data() -> dict[str, Any]:
    profile = load_profile()

    if not isinstance(profile, dict):
        profile = {}

    profile.setdefault(SYNC_IDS_KEY, [])
    profile.setdefault(SYNC_COUNT_KEY, 0)
    profile.setdefault(LAST_SYNC_KEY, "")

    return profile


def _save_profile_data(profile: dict[str, Any]) -> None:
    save_profile(profile)


# -------------------------
# API HELPERS
# -------------------------

def _request_json(url: str) -> dict[str, Any]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_archives(username: str) -> list[str]:
    username = (username or "").strip().lower()
    if not username:
        return []

    url = f"{BASE_URL}/{username}/games/archives"
    data = _request_json(url)

    archives = data.get("archives", [])
    if not isinstance(archives, list):
        return []

    return [a for a in archives if isinstance(a, str)]


def get_games_from_archive(archive_url: str) -> list[dict[str, Any]]:
    data = _request_json(archive_url)

    games = data.get("games", [])
    if not isinstance(games, list):
        return []

    return [g for g in games if isinstance(g, dict)]


# -------------------------
# CORE SYNC LOGIC
# -------------------------

def _game_fingerprint(game: dict[str, Any]) -> str:
    return str(
        game.get("url")
        or game.get("uuid")
        or game.get("end_time")
        or (game.get("pgn", "")[:120])
    )


def sync_chesscom_profile(
    username: str | None = None,
    max_games: int = 5
) -> list[dict[str, Any]]:

    profile = _load_profile_data()

    if not username:
        username = profile.get("chesscom_username", "")

    username = (username or "").strip().lower()
    if not username:
        return []

    seen_ids = set(profile.get(SYNC_IDS_KEY, []))

    archives = list(reversed(get_archives(username)))

    new_games: list[dict[str, Any]] = []

    for archive_url in archives:

        if len(new_games) >= max_games:
            break

        games = get_games_from_archive(archive_url)
        games = list(reversed(games))

        for game in games:

            if len(new_games) >= max_games:
                break

            fp = _game_fingerprint(game)

            if not fp or fp in seen_ids:
                continue

            pgn = game.get("pgn", "")
            if not isinstance(pgn, str) or not pgn.strip():
                continue

            new_games.append(game)
            seen_ids.add(fp)

    # -------------------------
    # KEEP STATE CLEAN
    # -------------------------

    profile[SYNC_IDS_KEY] = list(seen_ids)[-800:]
    profile[SYNC_COUNT_KEY] = len(profile[SYNC_IDS_KEY])

    if new_games:
        profile[LAST_SYNC_KEY] = str(
            new_games[0].get("end_time", "")
            or new_games[0].get("url", "")
        )

    _save_profile_data(profile)

    return new_games
