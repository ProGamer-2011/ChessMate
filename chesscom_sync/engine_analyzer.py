import io
import math
import os
import re
import statistics
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
import chess
import chess.engine
import chess.pgn
from player_profile.profile_manager import load_profile

ANALYZED_IDS_KEY = "chesscom_analyzed_game_urls"
ANALYZED_COUNT_KEY = "chesscom_analyzed_game_count"
LAST_SYNC_KEY = "last_chesscom_analysis_sync"
OPENING_REPERTOIRE_KEY = "opening_repertoire"
FACTUAL_PROFILE_KEY = "chesscom_factual_profile"
RECENT_GAMES_KEY = "recent_games"
RECENT_MOVE_SAMPLES_KEY = "recent_move_samples"
AI_READY_KEY = "chesscom_engine_ai_ready_payload"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STOCKFISH_PATH = os.path.abspath(
    os.path.join(BASE_DIR, "..", "engine", "stockfish.exe")
)

CLOCK_RE = re.compile(r"\[%clk\s+([0-9:.]+)\]")


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> int:
    return int(max(low, min(high, round(value))))


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _ensure_profile_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
    profile.setdefault(ANALYZED_IDS_KEY, [])
    profile.setdefault(ANALYZED_COUNT_KEY, 0)
    profile.setdefault(LAST_SYNC_KEY, "")
    profile.setdefault(OPENING_REPERTOIRE_KEY, {})
    profile.setdefault(FACTUAL_PROFILE_KEY, {})
    profile.setdefault(RECENT_GAMES_KEY, [])
    profile.setdefault(RECENT_MOVE_SAMPLES_KEY, [])

    factual = profile[FACTUAL_PROFILE_KEY]
    if not isinstance(factual, dict):
        factual = {}
        profile[FACTUAL_PROFILE_KEY] = factual

    factual.setdefault("opening", _empty_phase_bucket())
    factual.setdefault("middlegame", _empty_phase_bucket())
    factual.setdefault(
        "endgame",
        {
            **_empty_phase_bucket(),
            "king_moves": 0,
        },
    )

    defaults = {
        "total_games": 0,
        "total_moves": 0,
        "white_games": 0,
        "black_games": 0,
        "draw_games": 0,
        "win_games": 0,
        "loss_games": 0,
        "unknown_outcome_games": 0,
        "total_user_moves": 0,
        "total_opponent_moves": 0,
        "total_captures": 0,
        "total_checks": 0,
        "total_promotions": 0,
        "total_castles": 0,
        "total_quiet_moves": 0,
        "total_forcing_moves": 0,
        "total_trade_moves": 0,
        "total_pawn_moves": 0,
        "total_knight_moves": 0,
        "total_bishop_moves": 0,
        "total_rook_moves": 0,
        "total_queen_moves": 0,
        "total_king_moves": 0,
        "total_center_moves": 0,
        "total_development_moves": 0,
        "best_moves": 0,
        "excellent_moves": 0,
        "good_moves": 0,
        "inaccuracy_moves": 0,
        "mistake_moves": 0,
        "blunder_moves": 0,
        "average_centipawn_loss": 0.0,
        "median_centipawn_loss": 0.0,
        "opening_average_centipawn_loss": 0.0,
        "middlegame_average_centipawn_loss": 0.0,
        "endgame_average_centipawn_loss": 0.0,
        "opening_repertoire_diversity": 50,
        "average_user_clock_remaining": 0.0,
        "average_user_time_spent": 0.0,
        "average_opponent_clock_remaining": 0.0,
        "average_opponent_time_spent": 0.0,
        "time_trouble_moves": 0,
        "time_trouble_moves_under_30s": 0,
        "time_trouble_moves_under_15s": 0,
        "time_trouble_moves_under_10s": 0,
    }
    for key, value in defaults.items():
        factual.setdefault(key, value)

    return profile


def _game_fingerprint(game_data: Dict[str, Any], game: chess.pgn.Game) -> str:
    return str(
        game_data.get("url")
        or game_data.get("uuid")
        or game_data.get("end_time")
        or game.headers.get("Site", "")
        or game_data.get("pgn", "")[:180]
    )


def _user_color_from_headers(game: chess.pgn.Game, username: str) -> Optional[str]:
    white = (game.headers.get("White") or "").strip().lower()
    black = (game.headers.get("Black") or "").strip().lower()
    username = (username or "").strip().lower()

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
        return 1.0 if user_color == "white" else 0.0
    if result == "0-1":
        return 1.0 if user_color == "black" else 0.0
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


def _parse_time_control(time_control: str) -> Tuple[Optional[float], float]:
    text = (time_control or "").strip()
    if not text or text == "-":
        return None, 0.0
    if "+" in text:
        base_text, inc_text = text.split("+", 1)
        return _safe_float(base_text, 0.0), _safe_float(inc_text, 0.0)
    return _safe_float(text, 0.0), 0.0


def _parse_clock(comment: str) -> Optional[float]:
    if not comment:
        return None
    match = CLOCK_RE.search(comment)
    if not match:
        return None
    raw = match.group(1).strip()
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 1:
            return float(parts[0])
    except Exception:
        return None
    return None


def _phase(ply_index: int, board: chess.Board) -> str:
    piece_count = len(board.piece_map())
    if ply_index < 20 or piece_count >= 24 or board.fullmove_number <= 10:
        return "opening"
    if ply_index >= 40 or piece_count <= 14 or board.fullmove_number >= 40:
        return "endgame"
    return "middlegame"


def _piece_value(piece_type: Optional[int]) -> int:
    values = {
        chess.PAWN: 100,
        chess.KNIGHT: 300,
        chess.BISHOP: 300,
        chess.ROOK: 500,
        chess.QUEEN: 900,
        chess.KING: 0,
    }
    return values.get(piece_type, 0)


def _piece_name(piece_type: Optional[int]) -> str:
    return {
        chess.PAWN: "pawn",
        chess.KNIGHT: "knight",
        chess.BISHOP: "bishop",
        chess.ROOK: "rook",
        chess.QUEEN: "queen",
        chess.KING: "king",
    }.get(piece_type, "")


def _is_center_square(square: int) -> bool:
    return square in {chess.D4, chess.E4, chess.D5, chess.E5}


def _move_features(board: chess.Board, move: chess.Move, phase: str) -> Dict[str, Any]:
    piece = board.piece_at(move.from_square)
    piece_type = piece.piece_type if piece is not None else None
    target_piece = board.piece_at(move.to_square)

    capture = board.is_capture(move)
    check = board.gives_check(move)
    castle = board.is_castling(move)
    promotion = move.promotion is not None
    quiet = not capture and not check and not castle and not promotion
    center = _is_center_square(move.to_square)

    development = (
        phase == "opening"
        and piece_type in (chess.KNIGHT, chess.BISHOP)
        and move.from_square in {
            chess.B1, chess.G1, chess.C1, chess.F1,
            chess.B8, chess.G8, chess.C8, chess.F8,
        }
    )

    target_value = _piece_value(target_piece.piece_type) if target_piece else 0
    moving_value = _piece_value(piece_type) if piece_type is not None else 0
    sacrifice_like = (
        piece is not None
        and piece_type != chess.PAWN
        and capture
        and target_value < moving_value
    )

    return {
        "piece_type": piece_type,
        "piece_name": _piece_name(piece_type),
        "capture": capture,
        "check": check,
        "castle": castle,
        "promotion": promotion,
        "quiet": quiet,
        "center": center,
        "development": development,
        "forcing": capture or check or promotion,
        "sacrifice_like": sacrifice_like,
        "target_piece_type": target_piece.piece_type if target_piece else None,
    }


def _score_to_cp_for_turn(score_obj: chess.engine.PovScore, turn: bool) -> int:
    pov = score_obj.pov(turn)
    cp = pov.score()
    if cp is not None:
        return int(cp)
    mate = pov.mate()
    if mate is None:
        return 0
    return 100000 if mate > 0 else -100000

def _calculate_cpl(
    best_score: chess.engine.PovScore,
    played_score: chess.engine.PovScore,
    turn: bool,
) -> int:

    best = best_score.pov(turn)
    played = played_score.pov(turn)

    best_mate = best.mate()
    played_mate = played.mate()

    if best_mate is None and played_mate is None:
        best_cp = best.score(mate_score=100000) or 0
        played_cp = played.score(mate_score=100000) or 0
        return max(0, best_cp - played_cp)

    if best_mate is not None and played_mate is not None:

        if best_mate > 0 and played_mate > 0:

            if played_mate >= best_mate:
                return 0

            return (best_mate - played_mate) * 25

        if best_mate < 0 and played_mate < 0:

            if played_mate < best_mate:
                return 0

            return (played_mate - best_mate) * 25

        return 5000

    if best_mate is not None and played_mate is None:

        if best_mate > 0:
            return 1200

        return 0

    if best_mate is None and played_mate is not None:

        if played_mate > 0:
            return 0

        return 1200

    return 0

def _safe_san(board: chess.Board, move: chess.Move) -> str:
    try:
        return board.san(move)
    except Exception:
        return ""


def _engine_analyse(
    engine: chess.engine.SimpleEngine,
    board: chess.Board,
    depth: int,
    multipv: int,
) -> List[Dict[str, Any]]:
    try:
        info = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
    except Exception:
        return []

    if isinstance(info, dict):
        return [info]
    if isinstance(info, list):
        return [x for x in info if isinstance(x, dict)]
    return []


def _find_rank_for_move(lines: List[Dict[str, Any]], move: chess.Move) -> Optional[int]:
    for idx, line in enumerate(lines, start=1):
        pv = line.get("pv") or []
        if pv and pv[0] == move:
            return idx
    return None


def _classify_quality(loss_cp: int, is_best: bool, move_features: Dict[str, Any], engine_rank: Optional[int]) -> str:
    if is_best or engine_rank == 1 or loss_cp <= 8:
        return "Best"
    if loss_cp <= 15:
        return "Excellent"
    if loss_cp <= 40:
        return "Good"
    if loss_cp <= 120:
        return "Inaccuracy"
    if loss_cp <= 250:
        return "Mistake"
    return "Blunder"


def _empty_phase_bucket():
    return {
        "moves": 0,
        "captures": 0,
        "checks": 0,
        "castles": 0,
        "promotions": 0,

        "development_moves": 0,
        "center_moves": 0,

        "average_cpl": 0.0,
        "median_cpl": 0.0,

        "best_moves": 0,
        "excellent_moves": 0,
        "good_moves": 0,
        "inaccuracies": 0,
        "mistakes": 0,
        "blunders": 0,
    }

def _empty_game_summary():

    return {

        "metadata": {
            "game_id": "",
            "headers": {},
            "user_color": "",
            "opening_name": "",
            "eco": "",
            "time_control": "",
            "rated": False,
            "time_class": "",
        },

        "result": {
            "outcome": "",
            "score": 0.5,
            "plies": 0,
            "user_moves": 0,
            "opponent_moves": 0,
        },

        "engine": {

            "accuracy": {
                "average_cpl": 0.0,
                "median_cpl": 0.0,
            },

            "quality": {
                "best": 0,
                "excellent": 0,
                "good": 0,
                "inaccuracy": 0,
                "mistake": 0,
                "blunder": 0,
            },

            "phase": {

                "opening": {
                    "moves":0,
                    "average_cpl":0,
                    "median_cpl":0
                },

                "middlegame":{
                    "moves":0,
                    "average_cpl":0,
                    "median_cpl":0
                },

                "endgame":{
                    "moves":0,
                    "average_cpl":0,
                    "median_cpl":0
                }
            }
        },

        "style": {

            "piece_moves":{
                "pawn":0,
                "knight":0,
                "bishop":0,
                "rook":0,
                "queen":0,
                "king":0,
            },

            "captures":0,
            "checks":0,
            "castles":0,
            "promotions":0,

            "quiet_moves":0,
            "forcing_moves":0,

            "center_moves":0,
            "development_moves":0,

            "trade_moves":0,

        },

        "time":{

            "average_remaining":0,

            "average_spent":0,

            "time_trouble":{
                "<30":0,
                "<15":0,
                "<10":0
            }

        },

        "moves":[]
    }

def _build_move_sample(
    *,
    game_id: str,
    ply_index: int,
    board_before: chess.Board,
    board_after: chess.Board,
    move: chess.Move,
    phase: str,
    mover_side: str,
    best_move: chess.Move,
    best_eval_cp: int,
    user_eval_cp: int,
    cpl: int,
    engine_rank: Optional[int],
    quality: str,
    clock_before: Optional[float],
    clock_after: Optional[float],
    time_spent: Optional[float],
    comment: str,
) -> Dict[str, Any]:
    features = _move_features(board_before, move, phase)
    return {
        "game_id": game_id,
        "move_index": ply_index,
        "fullmove_number": board_before.fullmove_number,
        "side": mover_side,
        "phase": phase,
        "fen_before": board_before.fen(),
        "fen_after": board_after.fen(),
        "san": _safe_san(board_before, move),
        "uci": move.uci(),
        "best_move_san": _safe_san(board_before, best_move),
        "best_move_uci": best_move.uci() if best_move else "",
        "best_eval_cp": best_eval_cp,
        "user_eval_cp": user_eval_cp,
        "centipawn_loss": cpl,
        "engine_rank": engine_rank,
        "quality": quality,
        "is_best_move": engine_rank == 1 or cpl <= 8,
        "is_capture": features["capture"],
        "is_check": features["check"],
        "is_castle": features["castle"],
        "is_promotion": features["promotion"],
        "is_quiet": features["quiet"],
        "is_center": features["center"],
        "is_development": features["development"],
        "is_sacrifice_like": features["sacrifice_like"],
        "piece": features["piece_name"],
        "clock_before": clock_before,
        "clock_after": clock_after,
        "time_spent": time_spent,
        "comment": comment,
    }


def _analyze_single_game(
    game_data: Dict[str, Any],
    username: str,
    engine: chess.engine.SimpleEngine,
    depth: int,
    multipv: int,
) -> Optional[Dict[str, Any]]:
    pgn_text = game_data.get("pgn")
    if not pgn_text or not isinstance(pgn_text, str) or not pgn_text.strip():
        return None

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None

    game_id = _game_fingerprint(game_data, game)
    user_color = _user_color_from_headers(game, username)

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
        "rated": game_data.get("rated", game.headers.get("Rated", "")),
        "time_class": game_data.get("time_class", ""),
    }

    base_seconds, increment_seconds = _parse_time_control(headers["time_control"])
    clock_state = {"white": base_seconds, "black": base_seconds}

    board = game.board()
    node = game
    ply_index = 0

    summary = _empty_game_summary()
    summary["headers"] = headers
    summary["game_id"] = game_id
    summary["user_color"] = user_color
    summary["result_score"] = _result_score_for_user(game, user_color)
    summary["result_text"] = headers["result"]
    summary["time_control"] = headers["time_control"]
    summary["opening_name"] = headers["opening"]
    summary["eco"] = headers["eco"]
    summary["rated"] = headers["rated"]
    summary["time_class"] = headers["time_class"]

    user_move_turn_numbers: List[int] = []
    user_move_indices: List[int] = []
    cpl_samples: List[int] = []
    move_samples: List[Dict[str, Any]] = []

    total_user_clock_remaining = 0.0
    total_user_time_spent = 0.0
    total_opponent_clock_remaining = 0.0
    total_opponent_time_spent = 0.0
    user_clock_samples = 0
    opponent_clock_samples = 0

    while node.variations:
        node = node.variation(0)
        move = node.move
        if move is None:
            break

        mover_side = "white" if board.turn == chess.WHITE else "black"
        phase = _phase(ply_index, board)

        analysis_before = _engine_analyse(engine, board, depth=depth, multipv=multipv)
        if not analysis_before:
            try:
                board.push(move)
            except Exception:
                break
            ply_index += 1
            continue

        best_line = analysis_before[0]
        pv = best_line.get("pv") or []
        best_move = pv[0] if pv else move

        best_eval_cp = _score_to_cp_for_turn(best_line["score"], board.turn)

        after_board = board.copy()
        try:
            after_board.push(move)
        except Exception:
            break

        analysis_after = _engine_analyse(engine, after_board, depth=8, multipv=1)

        if analysis_after:
            played_line = analysis_after[0]

            user_eval_cp = _score_to_cp_for_turn(
                played_line["score"],
                board.turn,
            )

            cpl = _calculate_cpl(
                best_line["score"],
                played_line["score"],
                board.turn,
            )
        else:
            user_eval_cp = -100000
            cpl = 1200

        engine_rank = _find_rank_for_move(analysis_before, move)
        quality = _classify_quality(cpl, engine_rank == 1, _move_features(board, move, phase), engine_rank)

        features = _move_features(board, move, phase)

        if user_color == mover_side:
            summary["user_moves"] += 1
            cpl_samples.append(cpl)
            user_move_turn_numbers.append(board.fullmove_number)
            user_move_indices.append(ply_index + 1)

            if summary["first_user_move_san"] is None:
                summary["first_user_move_san"] = _safe_san(board, move)
                summary["first_user_move_uci"] = move.uci()
                summary["first_user_move_number"] = board.fullmove_number

            if features["capture"]:
                summary["captures"] += 1
            if features["check"]:
                summary["checks"] += 1
            if features["promotion"]:
                summary["promotions"] += 1
            if features["castle"]:
                summary["castles"] += 1
            if features["quiet"]:
                summary["quiet_moves"] += 1
            if features["forcing"]:
                summary["forcing_moves"] += 1
            if features["center"]:
                summary["center_moves"] += 1
            if features["development"]:
                summary["development_moves"] += 1

            piece = board.piece_at(move.from_square)
            piece_type = piece.piece_type if piece is not None else None

            if piece_type == chess.PAWN:
                summary["pawn_moves"] += 1
            elif piece_type == chess.KNIGHT:
                summary["knight_moves"] += 1
            elif piece_type == chess.BISHOP:
                summary["bishop_moves"] += 1
            elif piece_type == chess.ROOK:
                summary["rook_moves"] += 1
            elif piece_type == chess.QUEEN:
                summary["queen_moves"] += 1
            elif piece_type == chess.KING:
                summary["king_moves"] += 1

            if board.is_capture(move) or board.is_en_passant(move):
                summary["trade_moves"] += 1

            if phase == "opening":
                summary["opening"]["moves"] += 1
                summary["opening"]["cpls"].append(cpl)
                if features["capture"]:
                    summary["opening"]["captures"] += 1
                if features["check"]:
                    summary["opening"]["checks"] += 1
                if features["castle"]:
                    summary["opening"]["castles"] += 1
                if features["promotion"]:
                    summary["opening"]["promotions"] += 1
                if features["development"]:
                    summary["opening"]["development_moves"] += 1
                if features["center"]:
                    summary["opening"]["center_moves"] += 1
            elif phase == "middlegame":
                summary["middlegame"]["moves"] += 1
                summary["middlegame"]["cpls"].append(cpl)
                if features["capture"]:
                    summary["middlegame"]["captures"] += 1
                if features["check"]:
                    summary["middlegame"]["checks"] += 1
                if features["castle"]:
                    summary["middlegame"]["castles"] += 1
                if features["promotion"]:
                    summary["middlegame"]["promotions"] += 1
            else:
                summary["endgame"]["moves"] += 1
                summary["endgame"]["cpls"].append(cpl)
                if features["capture"]:
                    summary["endgame"]["captures"] += 1
                if features["check"]:
                    summary["endgame"]["checks"] += 1
                if features["castle"]:
                    summary["endgame"]["castles"] += 1
                if features["promotion"]:
                    summary["endgame"]["promotions"] += 1
                if piece_type == chess.KING:
                    summary["endgame"]["king_moves"] += 1

            clock_after = _parse_clock(node.comment or "")
            clock_before = clock_state[mover_side]
            time_spent = None

            if clock_after is not None and clock_before is not None:
                time_spent = max(0.0, clock_before - clock_after + increment_seconds)
                clock_state[mover_side] = clock_after
                total_user_clock_remaining += clock_after
                total_user_time_spent += time_spent
                user_clock_samples += 1
                if clock_after <= 30:
                    summary["time_trouble_moves"] += 1
                    summary["time_trouble_moves_under_30s"] += 1
                if clock_after <= 15:
                    summary["time_trouble_moves_under_15s"] += 1
                if clock_after <= 10:
                    summary["time_trouble_moves_under_10s"] += 1

            move_samples.append(_build_move_sample(
                game_id=game_id,
                ply_index=ply_index + 1,
                board_before=board,
                board_after=after_board,
                move=move,
                phase=phase,
                mover_side=mover_side,
                best_move=best_move,
                best_eval_cp=best_eval_cp,
                user_eval_cp=user_eval_cp,
                cpl=cpl,
                engine_rank=engine_rank,
                quality=quality,
                clock_before=clock_before,
                clock_after=clock_after,
                time_spent=time_spent,
                comment=node.comment or "",
            ))

        else:
            summary["opponent_moves"] += 1
            if features["capture"]:
                summary["captures"] += 1
            if features["check"]:
                summary["checks"] += 1
            if features["promotion"]:
                summary["promotions"] += 1
            if features["castle"]:
                summary["castles"] += 1
            if features["quiet"]:
                summary["quiet_moves"] += 1
            if features["forcing"]:
                summary["forcing_moves"] += 1

            clock_after = _parse_clock(node.comment or "")
            clock_before = clock_state[mover_side]
            if clock_after is not None and clock_before is not None:
                time_spent = max(0.0, clock_before - clock_after + increment_seconds)
                clock_state[mover_side] = clock_after
                total_opponent_clock_remaining += clock_after
                total_opponent_time_spent += time_spent
                opponent_clock_samples += 1

        try:
            board.push(move)
        except Exception:
            break
        ply_index += 1

    summary["plies"] = ply_index

    if summary["result_text"] == "1/2-1/2":
        summary["outcome"] = "draw"
    elif summary["result_score"] >= 1.0:
        summary["outcome"] = "win"
    elif summary["result_score"] <= 0.0:
        summary["outcome"] = "loss"
    else:
        summary["outcome"] = "unknown"

    summary["cpl_samples"] = sorted(cpl_samples)
    summary["move_samples"] = move_samples

    summary["best_moves"] = sum(1 for c in cpl_samples if c <= 8)
    summary["excellent_moves"] = sum(1 for c in cpl_samples if 8 < c <= 15)
    summary["good_moves"] = sum(1 for c in cpl_samples if 15 < c <= 40)
    summary["inaccuracy_moves"] = sum(1 for c in cpl_samples if 40 < c <= 120)
    summary["mistake_moves"] = sum(1 for c in cpl_samples if 120 < c <= 250)
    summary["blunder_moves"] = sum(1 for c in cpl_samples if c > 250)

    summary["average_centipawn_loss"] = float(sum(cpl_samples) / len(cpl_samples)) if cpl_samples else 0.0
    summary["median_centipawn_loss"] = float(statistics.median(cpl_samples)) if cpl_samples else 0.0

    opening_cpls = summary["opening"]["cpls"]
    middlegame_cpls = summary["middlegame"]["cpls"]
    endgame_cpls = summary["endgame"]["cpls"]

    summary["average_user_clock_remaining"] = (
        total_user_clock_remaining / user_clock_samples if user_clock_samples else 0.0
    )
    summary["average_user_time_spent"] = (
        total_user_time_spent / user_clock_samples if user_clock_samples else 0.0
    )
    summary["average_opponent_clock_remaining"] = (
        total_opponent_clock_remaining / opponent_clock_samples if opponent_clock_samples else 0.0
    )
    summary["average_opponent_time_spent"] = (
        total_opponent_time_spent / opponent_clock_samples if opponent_clock_samples else 0.0
    )

    return summary


def _finalize_phase_bucket(bucket: Dict[str, Any]) -> None:
    cpls = bucket.get("cpls", [])
    if not isinstance(cpls, list):
        cpls = []
    if cpls:
        bucket["avg_cpl"] = float(sum(cpls) / len(cpls))
        bucket["median_cpl"] = float(statistics.median(cpls))
    else:
        bucket["avg_cpl"] = 0.0
        bucket["median_cpl"] = 0.0


def _recalculate_engine_profile(engine_profile: Dict[str, Any]) -> None:
    for phase_name in ("opening", "middlegame", "endgame"):
        bucket = engine_profile.get(phase_name, {})
        if isinstance(bucket, dict):
            _finalize_phase_bucket(bucket)

    all_cpls: List[int] = []
    for phase_name in ("opening", "middlegame", "endgame"):
        bucket = engine_profile.get(phase_name, {})
        if isinstance(bucket, dict):
            all_cpls.extend([_safe_int(x) for x in bucket.get("cpls", [])])

    if all_cpls:
        engine_profile["average_centipawn_loss"] = float(sum(all_cpls) / len(all_cpls))
        engine_profile["median_centipawn_loss"] = float(statistics.median(all_cpls))
    else:
        engine_profile["average_centipawn_loss"] = 0.0
        engine_profile["median_centipawn_loss"] = 0.0

    engine_profile["opening_average_centipawn_loss"] = float(engine_profile.get("opening", {}).get("avg_cpl", 0.0))
    engine_profile["middlegame_average_centipawn_loss"] = float(engine_profile.get("middlegame", {}).get("avg_cpl", 0.0))
    engine_profile["endgame_average_centipawn_loss"] = float(engine_profile.get("endgame", {}).get("avg_cpl", 0.0))


def _merge_game_into_profile(
    profile: Dict[str, Any],
    engine_profile: Dict[str, Any],
    summary: Dict[str, Any],
) -> None:
    engine_profile["total_games"] += 1
    engine_profile["total_moves"] += _safe_int(summary.get("plies", 0))
    engine_profile["total_user_moves"] += _safe_int(summary.get("user_moves", 0))
    engine_profile["total_opponent_moves"] += _safe_int(summary.get("opponent_moves", 0))
    engine_profile["total_captures"] += _safe_int(summary.get("captures", 0))
    engine_profile["total_checks"] += _safe_int(summary.get("checks", 0))
    engine_profile["total_promotions"] += _safe_int(summary.get("promotions", 0))
    engine_profile["total_castles"] += _safe_int(summary.get("castles", 0))
    engine_profile["total_quiet_moves"] += _safe_int(summary.get("quiet_moves", 0))
    engine_profile["total_forcing_moves"] += _safe_int(summary.get("forcing_moves", 0))
    engine_profile["total_trade_moves"] += _safe_int(summary.get("trade_moves", 0))
    engine_profile["total_pawn_moves"] += _safe_int(summary.get("pawn_moves", 0))
    engine_profile["total_knight_moves"] += _safe_int(summary.get("knight_moves", 0))
    engine_profile["total_bishop_moves"] += _safe_int(summary.get("bishop_moves", 0))
    engine_profile["total_rook_moves"] += _safe_int(summary.get("rook_moves", 0))
    engine_profile["total_queen_moves"] += _safe_int(summary.get("queen_moves", 0))
    engine_profile["total_king_moves"] += _safe_int(summary.get("king_moves", 0))
    engine_profile["total_center_moves"] += _safe_int(summary.get("center_moves", 0))
    engine_profile["total_development_moves"] += _safe_int(summary.get("development_moves", 0))

    outcome = summary.get("outcome")
    if outcome == "win":
        engine_profile["win_games"] += 1
    elif outcome == "loss":
        engine_profile["loss_games"] += 1
    elif outcome == "draw":
        engine_profile["draw_games"] += 1
    else:
        engine_profile["unknown_outcome_games"] += 1

    user_color = summary.get("user_color")
    if user_color == "white":
        engine_profile["white_games"] += 1
    elif user_color == "black":
        engine_profile["black_games"] += 1

    for key in ("best_moves", "excellent_moves", "good_moves", "inaccuracy_moves", "mistake_moves", "blunder_moves"):
        engine_profile[key] += _safe_int(summary.get(key, 0))

    for phase_name in ("opening", "middlegame", "endgame"):
        profile_bucket = engine_profile.get(phase_name, {})
        summary_bucket = summary.get(phase_name, {})
        if isinstance(profile_bucket, dict) and isinstance(summary_bucket, dict):
            profile_bucket["moves"] += _safe_int(summary_bucket.get("moves", 0))
            profile_bucket["captures"] += _safe_int(summary_bucket.get("captures", 0))
            profile_bucket["checks"] += _safe_int(summary_bucket.get("checks", 0))
            profile_bucket["castles"] += _safe_int(summary_bucket.get("castles", 0))
            profile_bucket["promotions"] += _safe_int(summary_bucket.get("promotions", 0))
            if "cpls" in profile_bucket:
                profile_bucket["cpls"].extend(summary_bucket.get("cpls", []))

    if "king_moves" in engine_profile.get("endgame", {}):
        engine_profile["endgame"]["king_moves"] += _safe_int(summary.get("endgame_king_moves", 0))

    engine_profile["average_user_clock_remaining"] = float(summary.get("average_user_clock_remaining", 0.0))
    engine_profile["average_user_time_spent"] = float(summary.get("average_user_time_spent", 0.0))
    engine_profile["average_opponent_clock_remaining"] = float(summary.get("average_opponent_clock_remaining", 0.0))
    engine_profile["average_opponent_time_spent"] = float(summary.get("average_opponent_time_spent", 0.0))

    engine_profile["time_trouble_moves"] += _safe_int(summary.get("time_trouble_moves", 0))
    engine_profile["time_trouble_moves_under_30s"] += _safe_int(summary.get("time_trouble_moves_under_30s", 0))
    engine_profile["time_trouble_moves_under_15s"] += _safe_int(summary.get("time_trouble_moves_under_15s", 0))
    engine_profile["time_trouble_moves_under_10s"] += _safe_int(summary.get("time_trouble_moves_under_10s", 0))

    profile[RECENT_GAMES_KEY].append({
        "game_id": summary["game_id"],
        "headers": summary["headers"],
        "user_color": summary["user_color"],
        "outcome": summary["outcome"],
        "result_score": summary["result_score"],
        "plies": summary["plies"],
        "user_moves": summary["user_moves"],
        "opponent_moves": summary["opponent_moves"],
        "captures": summary["captures"],
        "checks": summary["checks"],
        "promotions": summary["promotions"],
        "castles": summary["castles"],
        "quiet_moves": summary["quiet_moves"],
        "forcing_moves": summary["forcing_moves"],
        "trade_moves": summary["trade_moves"],
        "capture_rate": summary["capture_rate"],
        "check_rate": summary["check_rate"],
        "castle_rate": summary["castle_rate"],
        "promotion_rate": summary["promotion_rate"],
        "opening_name": summary["opening_name"],
        "eco": summary["eco"],
        "time_control": summary["time_control"],
        "average_centipawn_loss": summary["average_centipawn_loss"],
        "time_trouble_moves": summary["time_trouble_moves"],
    })
    profile[RECENT_GAMES_KEY] = profile[RECENT_GAMES_KEY][-25:]

    profile[RECENT_MOVE_SAMPLES_KEY].extend(summary.get("move_samples", []))
    profile[RECENT_MOVE_SAMPLES_KEY] = profile[RECENT_MOVE_SAMPLES_KEY][-100:]


def _build_ai_ready_payload(profile: Dict[str, Any]) -> Dict[str, Any]:
    factual = profile.get(FACTUAL_PROFILE_KEY, {})
    if not isinstance(factual, dict):
        factual = {}

    return {
        "summary": {
            "games_analyzed": _safe_int(profile.get("games_analyzed", 0)),
            "moves_analyzed": _safe_int(profile.get("moves_analyzed", 0)),
            "analyzed_game_count": _safe_int(profile.get(ANALYZED_COUNT_KEY, 0)),
            "last_sync": profile.get(LAST_SYNC_KEY, ""),
        },
        "opening_repertoire": profile.get(OPENING_REPERTOIRE_KEY, {}),
        "factual_profile": factual,
    }

def create_engine(engine_path: Optional[str] = None) -> chess.engine.SimpleEngine:
    path = os.path.abspath(engine_path or DEFAULT_STOCKFISH_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Stockfish not found at: {path}")
    return chess.engine.SimpleEngine.popen_uci(path)


def analyze_games(
    pgn_games,
    username: Optional[str] = None,
    *,
    engine: Optional[chess.engine.SimpleEngine] = None,
    engine_path: Optional[str] = None,
    depth: int = 10,
    multipv: int = 2,
    max_games: Optional[int] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    profile = load_profile()
    profile = _ensure_profile_defaults(profile)

    factual = profile[FACTUAL_PROFILE_KEY]
    if not isinstance(factual, dict):
        factual = {}
        profile[FACTUAL_PROFILE_KEY] = factual

    analyzed_ids = set(profile.get(ANALYZED_IDS_KEY, []))
    username = (username or "").strip().lower()

    created_engine = False
    if engine is None:
        engine = create_engine(engine_path=engine_path)
        created_engine = True

    new_games_processed = 0
    new_moves_processed = 0
    total_games_in_input = 0

    try:
        for game_data in pgn_games:
            if max_games is not None and new_games_processed >= max_games:
                break

            if isinstance(game_data, str):
                game_data = {"pgn": game_data}
            if not isinstance(game_data, dict):
                continue

            pgn_text = game_data.get("pgn")
            if not pgn_text or not isinstance(pgn_text, str) or not pgn_text.strip():
                continue

            game = chess.pgn.read_game(io.StringIO(pgn_text))
            if game is None:
                continue

            total_games_in_input += 1

            game_id = _game_fingerprint(game_data, game)
            if game_id in analyzed_ids:
                continue

            summary = _analyze_single_game(
                game_data=game_data,
                username=username,
                engine=engine,
                depth=depth,
                multipv=multipv,
            )
            if summary is None:
                continue

            analyzed_ids.add(game_id)
            new_games_processed += 1
            new_moves_processed += _safe_int(summary.get("plies", 0))

            factual["total_games"] += 1
            factual["total_moves"] += _safe_int(summary.get("plies", 0))
            factual["white_games"] += 1 if summary.get("user_color") == "white" else 0
            factual["black_games"] += 1 if summary.get("user_color") == "black" else 0
            factual["draw_games"] += 1 if summary.get("outcome") == "draw" else 0
            factual["win_games"] += 1 if summary.get("outcome") == "win" else 0
            factual["loss_games"] += 1 if summary.get("outcome") == "loss" else 0
            factual["unknown_outcome_games"] += 1 if summary.get("outcome") == "unknown" else 0

            factual["total_user_moves"] += _safe_int(summary.get("user_moves", 0))
            factual["total_opponent_moves"] += _safe_int(summary.get("opponent_moves", 0))
            factual["total_captures"] += _safe_int(summary.get("captures", 0))
            factual["total_checks"] += _safe_int(summary.get("checks", 0))
            factual["total_promotions"] += _safe_int(summary.get("promotions", 0))
            factual["total_castles"] += _safe_int(summary.get("castles", 0))
            factual["total_quiet_moves"] += _safe_int(summary.get("quiet_moves", 0))
            factual["total_forcing_moves"] += _safe_int(summary.get("forcing_moves", 0))
            factual["total_trade_moves"] += _safe_int(summary.get("trade_moves", 0))
            factual["total_pawn_moves"] += _safe_int(summary.get("pawn_moves", 0))
            factual["total_knight_moves"] += _safe_int(summary.get("knight_moves", 0))
            factual["total_bishop_moves"] += _safe_int(summary.get("bishop_moves", 0))
            factual["total_rook_moves"] += _safe_int(summary.get("rook_moves", 0))
            factual["total_queen_moves"] += _safe_int(summary.get("queen_moves", 0))
            factual["total_king_moves"] += _safe_int(summary.get("king_moves", 0))
            factual["total_center_moves"] += _safe_int(summary.get("center_moves", 0))
            factual["total_development_moves"] += _safe_int(summary.get("development_moves", 0))
            factual["best_moves"] += _safe_int(summary.get("best_moves", 0))
            factual["excellent_moves"] += _safe_int(summary.get("excellent_moves", 0))
            factual["good_moves"] += _safe_int(summary.get("good_moves", 0))
            factual["inaccuracy_moves"] += _safe_int(summary.get("inaccuracy_moves", 0))
            factual["mistake_moves"] += _safe_int(summary.get("mistake_moves", 0))
            factual["blunder_moves"] += _safe_int(summary.get("blunder_moves", 0))

            factual["average_centipawn_loss"] = float(
                summary.get("average_centipawn_loss", factual["average_centipawn_loss"])
            )
            factual["median_centipawn_loss"] = float(
                summary.get("median_centipawn_loss", factual["median_centipawn_loss"])
            )
            factual["opening_average_centipawn_loss"] = float(
                summary.get("opening_average_centipawn_loss", factual["opening_average_centipawn_loss"])
            )
            factual["middlegame_average_centipawn_loss"] = float(
                summary.get("middlegame_average_centipawn_loss", factual["middlegame_average_centipawn_loss"])
            )
            factual["endgame_average_centipawn_loss"] = float(
                summary.get("endgame_average_centipawn_loss", factual["endgame_average_centipawn_loss"])
            )

            factual["average_user_clock_remaining"] = float(
                summary.get("average_user_clock_remaining", factual["average_user_clock_remaining"])
            )
            factual["average_user_time_spent"] = float(
                summary.get("average_user_time_spent", factual["average_user_time_spent"])
            )
            factual["average_opponent_clock_remaining"] = float(
                summary.get("average_opponent_clock_remaining", factual["average_opponent_clock_remaining"])
            )
            factual["average_opponent_time_spent"] = float(
                summary.get("average_opponent_time_spent", factual["average_opponent_time_spent"])
            )

            factual["time_trouble_moves"] += _safe_int(summary.get("time_trouble_moves", 0))
            factual["time_trouble_moves_under_30s"] += _safe_int(summary.get("time_trouble_moves_under_30s", 0))
            factual["time_trouble_moves_under_15s"] += _safe_int(summary.get("time_trouble_moves_under_15s", 0))
            factual["time_trouble_moves_under_10s"] += _safe_int(summary.get("time_trouble_moves_under_10s", 0))

            _update_repertoire(profile, summary.get("first_user_move_san"))

            for phase_name in ("opening", "middlegame", "endgame"):
                factual.setdefault(phase_name, _empty_phase_bucket())

            for phase_name in ("opening", "middlegame", "endgame"):
                fbucket = factual[phase_name]
                sbucket = summary[phase_name]
                fbucket["moves"] += _safe_int(sbucket.get("moves", 0))
                fbucket["captures"] += _safe_int(sbucket.get("captures", 0))
                fbucket["checks"] += _safe_int(sbucket.get("checks", 0))
                fbucket["castles"] += _safe_int(sbucket.get("castles", 0))
                fbucket["promotions"] += _safe_int(sbucket.get("promotions", 0))
                if "cpls" not in fbucket:
                    fbucket["cpls"] = []
                fbucket["cpls"].extend(sbucket.get("cpls", []))

            factual["opening_repertoire_diversity"] = _repertoire_diversity(profile.get(OPENING_REPERTOIRE_KEY, {}))

            profile[RECENT_GAMES_KEY].append({
                "game_id": summary["game_id"],
                "headers": summary["headers"],
                "user_color": summary["user_color"],
                "outcome": summary["outcome"],
                "result_score": summary["result_score"],
                "plies": summary["plies"],
                "user_moves": summary["user_moves"],
                "opponent_moves": summary["opponent_moves"],
                "captures": summary["captures"],
                "checks": summary["checks"],
                "promotions": summary["promotions"],
                "castles": summary["castles"],
                "quiet_moves": summary["quiet_moves"],
                "forcing_moves": summary["forcing_moves"],
                "trade_moves": summary["trade_moves"],
                "capture_rate": summary["capture_rate"],
                "check_rate": summary["check_rate"],
                "castle_rate": summary["castle_rate"],
                "promotion_rate": summary["promotion_rate"],
                "opening_name": summary["opening_name"],
                "eco": summary["eco"],
                "time_control": summary["time_control"],
                "average_centipawn_loss": summary["average_centipawn_loss"],
                "time_trouble_moves": summary["time_trouble_moves"],
            })
            profile[RECENT_GAMES_KEY] = profile[RECENT_GAMES_KEY][-100:]

            profile[RECENT_MOVE_SAMPLES_KEY].extend(summary.get("move_samples", []))
            profile[RECENT_MOVE_SAMPLES_KEY] = profile[RECENT_MOVE_SAMPLES_KEY][-1000:]

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

        factual["total_games"] = _safe_int(factual.get("total_games", 0))
        factual["total_moves"] = _safe_int(factual.get("total_moves", 0))

        _recalculate_engine_profile(factual)
        for phase in ("opening","middlegame","endgame"):
            factual[phase]["cpls"] = []
        profile[FACTUAL_PROFILE_KEY] = factual
        profile[AI_READY_KEY] = _build_ai_ready_payload(profile)

        return {
            "games_analyzed": new_games_processed,
            "moves_analyzed": new_moves_processed,
            "input_games_seen": total_games_in_input,
            "analyzed_game_count": len(analyzed_ids_list),
            "profile_updated": True,
            "ai_ready_payload": profile[AI_READY_KEY],
            "factual_profile": factual,
        }

    finally:
        if created_engine and engine is not None:
            try:
                engine.quit()
            except Exception:
                pass


def build_ai_ready_payload(profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if profile is None:
        profile = load_profile()
    profile = _ensure_profile_defaults(profile)
    factual = profile.get(FACTUAL_PROFILE_KEY, {})
    if not isinstance(factual, dict):
        factual = {}
    profile[AI_READY_KEY] = _build_ai_ready_payload(profile)
    return profile[AI_READY_KEY]
