import io
import math
from collections import Counter
from typing import Any, Dict, List, Optional
import chess
import chess.pgn

from player_profile.profile_manager import load_profile

ANALYZED_IDS_KEY = "chesscom_analyzed_game_urls"
ANALYZED_COUNT_KEY = "chesscom_analyzed_game_count"
LAST_SYNC_KEY = "last_chesscom_analysis_sync"
OPENING_REPERTOIRE_KEY = "opening_repertoire"
FACTUAL_PROFILE_KEY = "chesscom_factual_profile"
AI_READY_KEY = "chesscom_engine_ai_ready_payload"
RECENT_GAMES_KEY = "recent_games"

def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> int:
    return int(max(low, min(high, round(value))))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _ensure_profile_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    profile.setdefault(ANALYZED_IDS_KEY, [])
    profile.setdefault(ANALYZED_COUNT_KEY, 0)
    profile.setdefault(LAST_SYNC_KEY, "")
    profile.setdefault(OPENING_REPERTOIRE_KEY, {})
    profile.setdefault(FACTUAL_PROFILE_KEY, {})

    factual = profile[FACTUAL_PROFILE_KEY]
    if not isinstance(factual, dict):
        factual = {}
        profile[FACTUAL_PROFILE_KEY] = factual

    defaults = _empty_aggregate()

    for key, value in defaults.items():

        if key not in factual:
            factual[key] = value

        elif isinstance(value, dict) and isinstance(factual[key], dict):

            for sub_key, sub_value in value.items():
                factual[key].setdefault(sub_key, sub_value)

    return profile

def _game_fingerprint(game_data: Dict[str, Any], game: chess.pgn.Game) -> str:
    return str(
        game_data.get("url")
        or game_data.get("uuid")
        or game_data.get("end_time")
        or game.headers.get("Site", "")
        or game_data.get("pgn", "")[:160]
    )


def _user_color_from_headers(game: chess.pgn.Game, username: str) -> Optional[str]:
    white = (game.headers.get("White") or "").strip().lower()
    black = (game.headers.get("Black") or "").strip().lower()
    username = username.strip().lower()

    if username and username == white:
        return "white"
    if username and username == black:
        return "black"
    return None


def _result_score_for_user(game: chess.pgn.Game, user_color: Optional[str]) -> float:
    result = (game.headers.get("Result") or "").strip()

    if result == "1/2-1/2":
        return 0.5

    if result == "1-0":
        if user_color == "white":
            return 1.0
        if user_color == "black":
            return 0.0

    if result == "0-1":
        if user_color == "black":
            return 1.0
        if user_color == "white":
            return 0.0

    return 0.5


def _update_repertoire(profile: Dict[str, Any], first_user_move_san: Optional[str]) -> None:
    if not first_user_move_san:
        return

    repertoire = profile.setdefault(OPENING_REPERTOIRE_KEY, {})
    if not isinstance(repertoire, dict):
        repertoire = {}
        profile[OPENING_REPERTOIRE_KEY] = repertoire

    repertoire[first_user_move_san] = int(repertoire.get(first_user_move_san, 0)) + 1


def _repertoire_diversity(repertoire: Dict[str, Any]) -> int:
    if not repertoire:
        return 50

    counts = [int(v) for v in repertoire.values() if _safe_int(v, 0) > 0]
    if not counts:
        return 50

    total = sum(counts)
    if total <= 0:
        return 50

    entropy = 0.0
    for count in counts:
        p = count / total
        entropy -= p * math.log(p + 1e-12)

    max_entropy = math.log(len(counts) + 1e-12) if len(counts) > 1 else 1.0
    normalized = 0.0 if max_entropy <= 0 else entropy / max_entropy

    return _clamp(20 + normalized * 80)


def _piece_key(piece_type: Optional[int]) -> Optional[str]:
    mapping = {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king",
    }
    return mapping.get(piece_type)


def _phase_from_ply_and_material(ply_index: int, board: chess.Board) -> str:
    piece_count = len(board.piece_map())

    if ply_index < 20 or piece_count >= 24:
        return "opening"
    if ply_index >= 40 or piece_count <= 14:
        return "endgame"
    return "middlegame"


def _analyze_game_factually(game: chess.pgn.Game, username: str) -> Dict[str, Any]:
    user_color = _user_color_from_headers(game, username)
    board = game.board()

    headers = {
        "site": game.headers.get("Site", ""),
        "event": game.headers.get("Event", ""),
        "date": game.headers.get("Date", ""),
        "utc_date": game.headers.get("UTCDate", ""),
        "utc_time": game.headers.get("UTCTime", ""),
        "end_date": game.headers.get("EndDate", ""),
        "white": game.headers.get("White", ""),
        "black": game.headers.get("Black", ""),
        "result": game.headers.get("Result", ""),
        "eco": game.headers.get("ECO", ""),
        "opening": game.headers.get("Opening", ""),
        "termination": game.headers.get("Termination", ""),
        "time_control": game.headers.get("TimeControl", ""),
    }

    plies = 0
    user_moves = 0
    opponent_moves = 0

    captures = 0
    checks = 0
    promotions = 0
    castles = 0
    quiet_moves = 0
    forcing_moves = 0
    trade_moves = 0

    non_pawn_moves = 0
    pawn_moves = 0
    knight_moves = 0
    bishop_moves = 0
    rook_moves = 0
    queen_moves = 0
    king_moves = 0

    captured_piece_counts = Counter()
    piece_types_moved = set()

    opening_user_moves = 0
    opening_captures = 0
    opening_checks = 0
    opening_castles = 0
    opening_promotions = 0
    opening_development_moves = 0
    opening_center_moves = 0

    middlegame_user_moves = 0
    middlegame_captures = 0
    middlegame_checks = 0
    middlegame_castles = 0
    middlegame_promotions = 0

    endgame_user_moves = 0
    endgame_captures = 0
    endgame_checks = 0
    endgame_castles = 0
    endgame_promotions = 0
    endgame_king_moves = 0

    first_user_move_san = None
    first_user_move_uci = None
    first_user_move_number = None
    opening_user_moves_san: List[str] = []

    user_move_turn_numbers: List[int] = []
    user_move_indices: List[int] = []

    for move in game.mainline_moves():
        is_user_turn = False
        if user_color == "white" and board.turn == chess.WHITE:
            is_user_turn = True
        elif user_color == "black" and board.turn == chess.BLACK:
            is_user_turn = True

        phase = _phase_from_ply_and_material(plies, board)

        if is_user_turn:
            user_moves += 1
            user_move_turn_numbers.append(board.fullmove_number)
            user_move_indices.append(plies + 1)

            piece = board.piece_at(move.from_square)
            piece_type = piece.piece_type if piece is not None else None
            piece_key = _piece_key(piece_type)

            if piece is not None:
                piece_types_moved.add(piece.symbol().lower())

            if piece_type is not None:
                if piece_key == "pawn":
                    pawn_moves += 1
                elif piece_key == "knight":
                    knight_moves += 1
                elif piece_key == "bishop":
                    bishop_moves += 1
                elif piece_key == "rook":
                    rook_moves += 1
                elif piece_key == "queen":
                    queen_moves += 1
                elif piece_key == "king":
                    king_moves += 1

                if piece_type != chess.PAWN:
                    non_pawn_moves += 1

            if first_user_move_san is None:
                try:
                    first_user_move_san = board.san(move)
                    first_user_move_uci = move.uci()
                    first_user_move_number = board.fullmove_number
                except Exception:
                    first_user_move_san = None
                    first_user_move_uci = None
                    first_user_move_number = None

            is_capture = board.is_capture(move)
            is_check = board.gives_check(move)
            is_castle = board.is_castling(move)
            is_promotion = move.promotion is not None
            is_quiet = not is_capture and not is_check and not is_castle and not is_promotion
            is_forcing = is_capture or is_check or is_promotion

            if is_capture:
                captures += 1
            if is_check:
                checks += 1
            if is_promotion:
                promotions += 1
            if is_castle:
                castles += 1
            if is_quiet:
                quiet_moves += 1
            if is_forcing:
                forcing_moves += 1

            captured_piece = board.piece_at(move.to_square)
            if board.is_en_passant(move):
                captured_piece_counts["pawn"] += 1
                trade_moves += 1
            elif captured_piece is not None:
                captured_key = _piece_key(captured_piece.piece_type)
                if captured_key:
                    captured_piece_counts[captured_key] += 1
                trade_moves += 1

            if phase == "opening":
                opening_user_moves += 1
                if is_capture:
                    opening_captures += 1
                if is_check:
                    opening_checks += 1
                if is_castle:
                    opening_castles += 1
                if is_promotion:
                    opening_promotions += 1

                from_square = move.from_square
                if piece_type in (chess.KNIGHT, chess.BISHOP):
                    if from_square in {
                        chess.B1, chess.G1, chess.C1, chess.F1,
                        chess.B8, chess.G8, chess.C8, chess.F8,
                    }:
                        opening_development_moves += 1

                if move.to_square in {chess.D4, chess.E4, chess.D5, chess.E5}:
                    opening_center_moves += 1

            elif phase == "middlegame":
                middlegame_user_moves += 1
                if is_capture:
                    middlegame_captures += 1
                if is_check:
                    middlegame_checks += 1
                if is_castle:
                    middlegame_castles += 1
                if is_promotion:
                    middlegame_promotions += 1

            else:
                endgame_user_moves += 1
                if is_capture:
                    endgame_captures += 1
                if is_check:
                    endgame_checks += 1
                if is_castle:
                    endgame_castles += 1
                if is_promotion:
                    endgame_promotions += 1
                if piece_key == "king":
                    endgame_king_moves += 1

            if len(opening_user_moves_san) < 10:
                try:
                    opening_user_moves_san.append(board.san(move))
                except Exception:
                    pass

        else:
            opponent_moves += 1

        try:
            board.push(move)
        except Exception:
            break

        plies += 1

    result_score = _result_score_for_user(game, user_color)
    result_text = (game.headers.get("Result") or "").strip()

    if result_text == "1/2-1/2":
        outcome = "draw"
    elif result_score >= 1.0:
        outcome = "win"
    elif result_score <= 0.0:
        outcome = "loss"
    else:
        outcome = "unknown"

    total_user_moves = max(1, user_moves)
    total_games_placeholder = 1  # per-game summary only

    capture_rate = captures / total_user_moves
    check_rate = checks / total_user_moves
    promotion_rate = promotions / total_user_moves
    castle_rate = castles / total_user_moves
    quiet_rate = quiet_moves / total_user_moves
    forcing_rate = forcing_moves / total_user_moves

    piece_move_counts = {
        "pawn": pawn_moves,
        "knight": knight_moves,
        "bishop": bishop_moves,
        "rook": rook_moves,
        "queen": queen_moves,
        "king": king_moves,
    }

    phase_counts = {
        "opening": {
            "moves": opening_user_moves,
            "captures": opening_captures,
            "checks": opening_checks,
            "castles": opening_castles,
            "promotions": opening_promotions,
            "development_moves": opening_development_moves,
            "center_moves": opening_center_moves,
        },
        "middlegame": {
            "moves": middlegame_user_moves,
            "captures": middlegame_captures,
            "checks": middlegame_checks,
            "castles": middlegame_castles,
            "promotions": middlegame_promotions,
        },
        "endgame": {
            "moves": endgame_user_moves,
            "captures": endgame_captures,
            "checks": endgame_checks,
            "castles": endgame_castles,
            "promotions": endgame_promotions,
            "king_moves": endgame_king_moves,
        },
    }

    average_user_move_index = 0.0
    if user_move_indices:
        average_user_move_index = sum(user_move_indices) / len(user_move_indices)

    average_user_turn_number = 0.0
    if user_move_turn_numbers:
        average_user_turn_number = sum(user_move_turn_numbers) / len(user_move_turn_numbers)

    return {
        "headers": headers,
        "game_id": _game_fingerprint({"url": headers["site"], "pgn": ""}, game),
        "user_color": user_color,
        "plies": plies,
        "user_moves": user_moves,
        "opponent_moves": opponent_moves,
        "outcome": outcome,
        "result_score": result_score,
        "result_text": result_text,
        "captures": captures,
        "checks": checks,
        "promotions": promotions,
        "castles": castles,
        "quiet_moves": quiet_moves,
        "forcing_moves": forcing_moves,
        "trade_moves": trade_moves,
        "capture_rate": capture_rate,
        "check_rate": check_rate,
        "promotion_rate": promotion_rate,
        "castle_rate": castle_rate,
        "quiet_rate": quiet_rate,
        "forcing_rate": forcing_rate,
        "non_pawn_moves": non_pawn_moves,
        "piece_move_counts": piece_move_counts,
        "captured_piece_counts": dict(captured_piece_counts),
        "piece_types_used": sorted(piece_types_moved),
        "opening_user_moves": opening_user_moves,
        "opening_captures": opening_captures,
        "opening_checks": opening_checks,
        "opening_castles": opening_castles,
        "opening_promotions": opening_promotions,
        "opening_development_moves": opening_development_moves,
        "opening_center_moves": opening_center_moves,
        "middlegame_user_moves": middlegame_user_moves,
        "middlegame_captures": middlegame_captures,
        "middlegame_checks": middlegame_checks,
        "middlegame_castles": middlegame_castles,
        "middlegame_promotions": middlegame_promotions,
        "endgame_user_moves": endgame_user_moves,
        "endgame_captures": endgame_captures,
        "endgame_checks": endgame_checks,
        "endgame_castles": endgame_castles,
        "endgame_promotions": endgame_promotions,
        "endgame_king_moves": endgame_king_moves,
        "first_user_move_san": first_user_move_san,
        "first_user_move_uci": first_user_move_uci,
        "first_user_move_number": first_user_move_number,
        "opening_user_moves_san": opening_user_moves_san,
        "average_user_move_index": average_user_move_index,
        "average_user_turn_number": average_user_turn_number,
        "time_control": headers["time_control"],
        "opening_name": headers["opening"],
        "eco": headers["eco"],
    }


def _empty_aggregate() -> Dict[str, Any]:
    return {
        "total_games": 0,
        "total_moves": 0,
        "white_games": 0,
        "black_games": 0,
        "draw_games": 0,
        "win_games": 0,
        "loss_games": 0,
        "total_user_moves": 0,
        "total_opponent_moves": 0,
        "total_captures": 0,
        "total_checks": 0,
        "total_promotions": 0,
        "total_castles": 0,
        "total_quiet_moves": 0,
        "total_forcing_moves": 0,
        "total_trade_moves": 0,
        "total_non_pawn_moves": 0,
        "piece_move_counts": {
            "pawn": 0,
            "knight": 0,
            "bishop": 0,
            "rook": 0,
            "queen": 0,
            "king": 0,
        },
        "captured_piece_counts": {
            "pawn": 0,
            "knight": 0,
            "bishop": 0,
            "rook": 0,
            "queen": 0,
            "king": 0,
        },
        "opening": {
            "moves": 0,
            "captures": 0,
            "checks": 0,
            "castles": 0,
            "promotions": 0,
            "development_moves": 0,
            "center_moves": 0,
        },
        "middlegame": {
            "moves": 0,
            "captures": 0,
            "checks": 0,
            "castles": 0,
            "promotions": 0,
        },
        "endgame": {
            "moves": 0,
            "captures": 0,
            "checks": 0,
            "castles": 0,
            "promotions": 0,
            "king_moves": 0,
        },
        "average_game_length": 0.0,
        "average_user_moves_per_game": 0.0,
        "average_capture_rate": 0.0,
        "average_check_rate": 0.0,
        "average_castle_rate": 0.0,
        "average_promotion_rate": 0.0,
        "average_quiet_rate": 0.0,
        "average_forcing_rate": 0.0,
        "average_user_move_index": 0.0,
        "average_user_turn_number": 0.0,
        "opening_repertoire_diversity": 50,
    }


def _merge_game_summary(aggregate: Dict[str, Any], signals: Dict[str, Any]) -> None:
    aggregate["total_games"] += 1
    aggregate["total_moves"] += _safe_int(signals.get("plies", 0))
    aggregate["total_user_moves"] += _safe_int(signals.get("user_moves", 0))
    aggregate["total_opponent_moves"] += _safe_int(signals.get("opponent_moves", 0))
    aggregate["total_captures"] += _safe_int(signals.get("captures", 0))
    aggregate["total_checks"] += _safe_int(signals.get("checks", 0))
    aggregate["total_promotions"] += _safe_int(signals.get("promotions", 0))
    aggregate["total_castles"] += _safe_int(signals.get("castles", 0))
    aggregate["total_quiet_moves"] += _safe_int(signals.get("quiet_moves", 0))
    aggregate["total_forcing_moves"] += _safe_int(signals.get("forcing_moves", 0))
    aggregate["total_trade_moves"] += _safe_int(signals.get("trade_moves", 0))
    aggregate["total_non_pawn_moves"] += _safe_int(signals.get("non_pawn_moves", 0))

    if signals.get("outcome") == "win":
        aggregate["win_games"] += 1
    elif signals.get("outcome") == "loss":
        aggregate["loss_games"] += 1
    elif signals.get("outcome") == "draw":
        aggregate["draw_games"] += 1

    if signals.get("user_color") == "white":
        aggregate["white_games"] += 1
    elif signals.get("user_color") == "black":
        aggregate["black_games"] += 1

    piece_counts = signals.get("piece_move_counts", {})
    for key in aggregate["piece_move_counts"]:
        aggregate["piece_move_counts"][key] += _safe_int(piece_counts.get(key, 0))

    captured_counts = signals.get("captured_piece_counts", {})
    for key in aggregate["captured_piece_counts"]:
        aggregate["captured_piece_counts"][key] += _safe_int(captured_counts.get(key, 0))

    for phase in ("opening", "middlegame", "endgame"):
        phase_data = signals.get(phase, {})
        agg_phase = aggregate[phase]
        for key in agg_phase:
            agg_phase[key] += _safe_int(phase_data.get(key, 0))

    aggregate["average_game_length"] = (
        aggregate["total_moves"] / max(1, aggregate["total_games"])
    )
    aggregate["average_user_moves_per_game"] = (
        aggregate["total_user_moves"] / max(1, aggregate["total_games"])
    )
    aggregate["average_capture_rate"] = (
        aggregate["total_captures"] / max(1, aggregate["total_user_moves"])
    )
    aggregate["average_check_rate"] = (
        aggregate["total_checks"] / max(1, aggregate["total_user_moves"])
    )
    aggregate["average_castle_rate"] = (
        aggregate["total_castles"] / max(1, aggregate["total_user_moves"])
    )
    aggregate["average_promotion_rate"] = (
        aggregate["total_promotions"] / max(1, aggregate["total_user_moves"])
    )
    aggregate["average_quiet_rate"] = (
        aggregate["total_quiet_moves"] / max(1, aggregate["total_user_moves"])
    )
    aggregate["average_forcing_rate"] = (
        aggregate["total_forcing_moves"] / max(1, aggregate["total_user_moves"])
    )

    total_opening_games = max(1, aggregate["opening"]["moves"])
    repertoire = aggregate.get(OPENING_REPERTOIRE_KEY, {})
    if not isinstance(repertoire, dict):
        repertoire = {}

    aggregate["opening_repertoire_diversity"] = _repertoire_diversity(repertoire)


def _build_ai_ready_payload(profile: Dict[str, Any]) -> Dict[str, Any]:
    factual = profile.get(FACTUAL_PROFILE_KEY, {})
    if not isinstance(factual, dict):
        factual = _empty_aggregate()
    else:
        defaults = _empty_aggregate()

        for key, value in defaults.items():

            if key not in factual:
                factual[key] = value

            elif isinstance(value, dict):
                if not isinstance(factual[key], dict):
                    factual[key] = {}

                for sub_key, sub_value in value.items():
                    factual[key].setdefault(sub_key, sub_value)

    payload = {
        "summary": {
            "games_analyzed": _safe_int(profile.get("games_analyzed", 0)),
            "moves_analyzed": _safe_int(profile.get("moves_analyzed", 0)),
            "analyzed_game_count": _safe_int(profile.get(ANALYZED_COUNT_KEY, 0)),
            "last_sync": profile.get(LAST_SYNC_KEY, ""),
        },
        "opening_repertoire": profile.get(OPENING_REPERTOIRE_KEY, {}),
        "factual_profile": factual,
    }

    return payload

def analyze_games(pgn_games, username=None):
    profile = load_profile()
    profile = _ensure_profile_defaults(profile)

    analyzed_ids = set(profile.get(ANALYZED_IDS_KEY, []))
    factual = profile[FACTUAL_PROFILE_KEY]
    if not isinstance(factual, dict):
        factual = _empty_aggregate()

    if username:
        username = username.strip().lower()

    total_games = 0
    total_moves = 0
    white_games = 0
    black_games = 0
    new_games_processed = 0
    new_moves_processed = 0
    total_games_in_input = 0

    recent_games = factual.get(RECENT_GAMES_KEY, [])
    if not isinstance(recent_games, list):
        recent_games = []

    for game_data in pgn_games:
        try:
            if isinstance(game_data, str):
                pgn_text = game_data
                game_data = {"pgn": pgn_text}
            elif not isinstance(game_data, dict):
                continue

            pgn_text = game_data.get("pgn")
            if not pgn_text or not isinstance(pgn_text, str) or not pgn_text.strip():
                continue

            game = chess.pgn.read_game(io.StringIO(pgn_text))
            if game is None:
                continue

            game_id = _game_fingerprint(game_data, game)
            if game_id in analyzed_ids:
                continue

            signals = _analyze_game_factually(game, username if username else "")
            _merge_game_summary(factual, signals)
            
            if signals["user_color"] == "white":
                white_games += 1
            elif signals["user_color"] == "black":
                black_games += 1

            total_games += 1
            total_moves += _safe_int(signals["plies"], 0)

            _update_repertoire(profile, signals.get("first_user_move_san"))

            analyzed_ids.add(game_id)
            new_games_processed += 1
            new_moves_processed += _safe_int(signals["plies"], 0)

            recent_games.append({
                "game_id": game_id
            })

        except Exception:
            continue

    analyzed_ids_list = list(analyzed_ids)[-1000:]
    profile[ANALYZED_IDS_KEY] = analyzed_ids_list
    profile[ANALYZED_COUNT_KEY] = len(analyzed_ids_list)

    if pgn_games:
        first_item = pgn_games[0]
        if isinstance(first_item, dict):
            profile[LAST_SYNC_KEY] = str(
                first_item.get("end_time", "")
                or first_item.get("url", "")
                or profile.get(LAST_SYNC_KEY, "")
            )

    profile["games_analyzed"] = _safe_int(profile.get("games_analyzed", 0)) + new_games_processed
    profile["moves_analyzed"] = _safe_int(profile.get("moves_analyzed", 0)) + new_moves_processed
    factual["opening_repertoire_diversity"] = _repertoire_diversity(profile.get(OPENING_REPERTOIRE_KEY, {}))

    profile[FACTUAL_PROFILE_KEY] = factual
    profile[AI_READY_KEY] = _build_ai_ready_payload(profile)

    return {
        "games_analyzed": new_games_processed,
        "moves_analyzed": new_moves_processed,
        "input_games_seen": total_games_in_input,
        "analyzed_game_count": len(analyzed_ids_list),
        "profile_updated": True,
        "ai_ready_payload": profile[AI_READY_KEY],
    }

def build_ai_ready_payload(profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if profile is None:
        profile = load_profile()

    profile = _ensure_profile_defaults(profile)
    return _build_ai_ready_payload(profile)
