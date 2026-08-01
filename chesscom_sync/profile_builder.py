from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from player_profile.profile_manager import load_profile

# Legacy shared key support
LEGACY_FACTUAL_KEY = "chesscom_factual_profile"

# Game analyzer keys
GAME_FACTUAL_KEY = "chesscom_game_factual_profile"
GAME_ANALYZED_IDS_KEY = "chesscom_game_analyzed_game_urls"
GAME_ANALYZED_COUNT_KEY = "chesscom_game_analyzed_game_count"
GAME_LAST_SYNC_KEY = "last_chesscom_game_sync"
GAME_AI_READY_KEY = "chesscom_game_ai_ready_payload"

# Engine analyzer keys
ENGINE_FACTUAL_KEY = "chesscom_engine_factual_profile"
ENGINE_ANALYZED_IDS_KEY = "chesscom_engine_analyzed_game_urls"
ENGINE_ANALYZED_COUNT_KEY = "chesscom_engine_analyzed_game_count"
ENGINE_LAST_SYNC_KEY = "last_chesscom_engine_sync"
ENGINE_AI_READY_KEY = "chesscom_engine_ai_ready_payload"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tail_list(items: Any, limit: int) -> list[Any]:
    if not isinstance(items, list) or limit <= 0:
        return []
    return items[-limit:]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_profile_data() -> Dict[str, Any]:
    profile = load_profile()
    if not isinstance(profile, dict):
        profile = {}

    profile.setdefault(GAME_ANALYZED_IDS_KEY, [])
    profile.setdefault(GAME_ANALYZED_COUNT_KEY, 0)
    profile.setdefault(GAME_LAST_SYNC_KEY, "")
    profile.setdefault(ENGINE_ANALYZED_IDS_KEY, [])
    profile.setdefault(ENGINE_ANALYZED_COUNT_KEY, 0)
    profile.setdefault(ENGINE_LAST_SYNC_KEY, "")

    profile.setdefault(GAME_FACTUAL_KEY, {})
    profile.setdefault(ENGINE_FACTUAL_KEY, {})
    profile.setdefault(LEGACY_FACTUAL_KEY, {})

    profile.setdefault(GAME_AI_READY_KEY, {})
    profile.setdefault(ENGINE_AI_READY_KEY, {})

    return profile


def _sanitize_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in profile.items():
        if key in {
            GAME_ANALYZED_IDS_KEY,
            ENGINE_ANALYZED_IDS_KEY,
        }:
            continue

        if isinstance(value, list) and len(value) > 200:
            clean[key] = value[-200:]
        else:
            clean[key] = value

    return clean


def _get_game_payload(profile: Dict[str, Any], result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(result, dict):
        payload = _safe_dict(result.get("ai_ready_payload"))
        if payload:
            return payload

        return {
            "summary": {
                "games_analyzed": _safe_int(result.get("games_analyzed", 0)),
                "moves_analyzed": _safe_int(result.get("moves_analyzed", 0)),
                "new_games_processed": _safe_int(result.get("new_games_processed", 0)),
                "new_moves_processed": _safe_int(result.get("new_moves_processed", 0)),
                "profile_updated": bool(result.get("profile_updated", False)),
            },
            "opening_repertoire": _safe_dict(profile.get("opening_repertoire", {})),
            "factual_profile": _safe_dict(
                result.get("factual_profile")
                or profile.get(GAME_FACTUAL_KEY)
                or profile.get(LEGACY_FACTUAL_KEY)
            ),
            "recent_games": _safe_list(result.get("recent_games")),
        }

    payload = _safe_dict(profile.get(GAME_AI_READY_KEY))
    if payload:
        return payload

    return {
        "summary": {},
        "opening_repertoire": _safe_dict(profile.get("opening_repertoire", {})),
        "factual_profile": _safe_dict(profile.get(GAME_FACTUAL_KEY) or profile.get(LEGACY_FACTUAL_KEY)),
        "recent_games": _safe_list(profile.get("recent_games", [])),
    }


def _get_engine_payload(profile: Dict[str, Any], result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(result, dict):
        payload = _safe_dict(result.get("ai_ready_payload"))
        if payload:
            return payload

        return {
            "summary": {
                "games_analyzed": _safe_int(result.get("games_analyzed", 0)),
                "moves_analyzed": _safe_int(result.get("moves_analyzed", 0)),
                "new_games_processed": _safe_int(result.get("new_games_processed", 0)),
                "new_moves_processed": _safe_int(result.get("new_moves_processed", 0)),
                "profile_updated": bool(result.get("profile_updated", False)),
            },
            "opening_repertoire": _safe_dict(profile.get("opening_repertoire", {})),
            "factual_profile": _safe_dict(
                result.get("factual_profile")
                or profile.get(ENGINE_FACTUAL_KEY)
            ),
            "recent_move_samples": _safe_list(result.get("recent_move_samples")),
        }

    payload = _safe_dict(profile.get(ENGINE_AI_READY_KEY))
    if payload:
        return payload

    return {
        "summary": {},
        "opening_repertoire": _safe_dict(profile.get("opening_repertoire", {})),
        "factual_profile": _safe_dict(profile.get(ENGINE_FACTUAL_KEY)),
        "recent_move_samples": _safe_list(profile.get("recent_move_samples", [])),
    }


def build_profile_bundle(
    profile: Optional[Dict[str, Any]] = None,
    *,
    game_result: Optional[Dict[str, Any]] = None,
    engine_result: Optional[Dict[str, Any]] = None,
    recent_games_limit: int = 25,
    recent_move_samples_limit: int = 100,
) -> Dict[str, Any]:
    if profile is None:
        profile = _load_profile_data()
    elif not isinstance(profile, dict):
        profile = {}

    profile = deepcopy(profile)
    current_profile = _sanitize_profile(profile)

    game_ai = _get_game_payload(profile, game_result)
    engine_ai = _get_engine_payload(profile, engine_result)

    game_recent = _tail_list(game_ai.get("recent_games", []), recent_games_limit)
    engine_recent = _tail_list(engine_ai.get("recent_move_samples", []), recent_move_samples_limit)

    bundle = {
        "metadata": {
            "generated_at": _utc_now_iso(),
            "profile_version": 1,
            "username": current_profile.get("chesscom_username", "") or current_profile.get("name", ""),
            "name": current_profile.get("name", ""),
            "rating": current_profile.get("rating", current_profile.get("chesscom_rating", 1000)),
        },
        "current_profile": current_profile,
        "game_analysis": {
            "summary": game_ai.get("summary", {}),
            "opening_repertoire": game_ai.get("opening_repertoire", current_profile.get("opening_repertoire", {})),
            "factual_profile": game_ai.get("factual_profile", _safe_dict(profile.get(GAME_FACTUAL_KEY))),
            "recent_games": game_recent,
        },
        "engine_analysis": {
            "summary": engine_ai.get("summary", {}),
            "opening_repertoire": engine_ai.get("opening_repertoire", current_profile.get("opening_repertoire", {})),
            "factual_profile": engine_ai.get("factual_profile", _safe_dict(profile.get(ENGINE_FACTUAL_KEY))),
            "recent_move_samples": engine_recent,
        },
    }

    return bundle


def print_profile_bundle(
    profile: Optional[Dict[str, Any]] = None,
    *,
    game_result: Optional[Dict[str, Any]] = None,
    engine_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bundle = build_profile_bundle(
        profile=profile,
        game_result=game_result,
        engine_result=engine_result,
    )

    print(
        json.dumps(
            bundle,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )
    return bundle


if __name__ == "__main__":
    print_profile_bundle()
