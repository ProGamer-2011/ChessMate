from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from player_profile.profile_manager import load_profile, save_profile
from updater.updater import Updater


class ChessMateHandler(BaseHTTPRequestHandler):
    server_version = "ChessMateAPI/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}

        raw = self.rfile.read(length)
        if not raw:
            return {}

        try:
            body = json.loads(raw.decode("utf-8"))
            return body if isinstance(body, dict) else {}
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            updater = Updater()
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "chessmate-python-backend",
                    "version": updater.get_version(),
                    "build": updater.get_build(),
                },
            )
            return

        if self.path == "/profile":
            self._send_json(200, {"ok": True, "profile": load_profile()})
            return

        self._send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/profile":
            payload = self._read_json_body()
            profile = payload.get("profile")
            if not isinstance(profile, dict):
                self._send_json(400, {"ok": False, "error": "profile object is required"})
                return

            save_profile(profile)
            self._send_json(200, {"ok": True, "profile": profile})
            return

        if self.path == "/analysis/run":
            payload = self._read_json_body()
            username = str(payload.get("username", "") or "").strip()
            max_games = int(payload.get("max_games", 5) or 5)

            if max_games < 1:
                max_games = 1

            if max_games > 20:
                max_games = 20

            try:
                from chesscom_sync.chesscom_sync import sync_chesscom_profile
                from chesscom_sync.engine_analyzer import analyze_games as engine_analyze_games
                from chesscom_sync.game_analyzer import analyze_games as factual_analyze_games
                from chesscom_sync.profile_builder import build_profile_bundle

                games = sync_chesscom_profile(username=username or None, max_games=max_games)

                factual_result = factual_analyze_games(games, username or None)
                engine_result = engine_analyze_games(games, username or None)

                bundle = build_profile_bundle(
                    profile=load_profile(),
                    game_result=factual_result,
                    engine_result=engine_result,
                )
            except Exception as error:
                self._send_json(500, {"ok": False, "error": str(error)})
                return

            self._send_json(
                200,
                {
                    "ok": True,
                    "games_synced": len(games),
                    "game_analysis": factual_result,
                    "engine_analysis": engine_result,
                    "bundle": bundle,
                },
            )
            return

        self._send_json(404, {"ok": False, "error": "Not found"})


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), ChessMateHandler)
    print(f"ChessMate backend running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
