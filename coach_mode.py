import time
from typing import Optional, Dict, Any, List
import chess
import chess.engine
from board_system.board_tracker import BoardTracker
from game_intelligence.player_model import PlayerModel


def _score_to_eval_text(score_obj: chess.engine.PovScore) -> str:
    score = score_obj.white()

    if score.is_mate():
        mate_in = score.mate()
        if mate_in is None:
            return "Mate"
        if mate_in > 0:
            return f"Mate in {mate_in}"
        return f"Mated in {abs(mate_in)}"

    cp = score.score(mate_score=10000)
    if cp is None:
        return "0.00"

    return f"{cp / 100.0:.2f}"


def _board_phase(board: chess.Board) -> str:
    piece_count = len(board.piece_map())

    if board.fullmove_number <= 10 or piece_count >= 24:
        return "opening"
    if piece_count <= 14 or board.fullmove_number >= 40:
        return "endgame"
    return "middlegame"


def _build_engine_data(
    board: chess.Board,
    move: chess.Move,
    move_error: float,
    phase: str
) -> Dict[str, Any]:
    piece = board.piece_at(move.from_square)

    return {
        "move_error": move_error,
        "is_capture": board.is_capture(move),
        "is_check": board.gives_check(move),
        "is_promotion": move.promotion is not None,
        "is_castle": board.is_castling(move),
        "is_sacrifice": (
            piece is not None
            and piece.piece_type != chess.PAWN
            and board.is_capture(move)
            and move_error >= 60
        ),
        "is_endgame": phase == "endgame",
        "is_opening": phase == "opening",
        "piece_moved": piece.symbol() if piece is not None else "",
        "phase": phase,
    }


def get_candidate_moves(
    board: chess.Board,
    engine: chess.engine.SimpleEngine,
    depth: int = 20,
    multipv: int = 12
) -> List[Dict[str, Any]]:

    candidates: List[Dict[str, Any]] = []

    try:
        info = engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            multipv=multipv
        )
    except Exception:
        return candidates

    for line in info:
        pv = line.get("pv")
        if not pv:
            continue

        move = pv[0]
        score_obj = line["score"].pov(board.turn)

        raw_score = score_obj.score(mate_score=10000)
        if raw_score is None:
            raw_score = 0

        if score_obj.is_mate():
            engine_score = 100.0
        else:
            engine_score = raw_score / 100.0

        piece = board.piece_at(move.from_square)

        candidates.append({
            "move": move,
            "engine_score": engine_score,
            "is_capture": board.is_capture(move),
            "gives_check": board.gives_check(move),
            "is_promotion": move.promotion is not None,
            "is_castle": board.is_castling(move),
            "piece_type": piece.piece_type if piece is not None else None,
            "raw_score": float(raw_score),
        })

    candidates.sort(
        key=lambda c: c["raw_score"],
        reverse=True
    )
    return candidates


def calculate_move_error(
    board: chess.Board,
    move: chess.Move,
    engine: chess.engine.SimpleEngine,
    player_model: PlayerModel
) -> int:
    analysis_depth = max(18, player_model.get_analysis_depth())
    turn = board.turn

    try:
        info = engine.analyse(
            board,
            chess.engine.Limit(depth=analysis_depth),
            multipv=1
        )
        best_score_cp = _score_to_cp_for_turn(info["score"], turn)
    except Exception:
        return 0

    try:
        moved_board = board.copy()
        moved_board.push(move)
        move_info = engine.analyse(
            moved_board,
            chess.engine.Limit(depth=analysis_depth),
            multipv=1
        )
        move_score_cp = _score_to_cp_for_turn(move_info["score"], turn)
    except Exception:
        move_score_cp = -10000

    return max(0, best_score_cp - move_score_cp)

def _score_to_cp_for_turn(
    score_obj: chess.engine.PovScore,
    turn: bool
) -> int:
    pov_score = score_obj.pov(turn)
    cp = pov_score.score(mate_score=10000)

    if cp is not None:
        return int(cp)

    mate = pov_score.mate()
    if mate is None:
        return 0

    return 10000 if mate > 0 else -10000

def _move_piece_value(piece_type: Optional[int]) -> int:
    values = {
        chess.PAWN: 100,
        chess.KNIGHT: 300,
        chess.BISHOP: 300,
        chess.ROOK: 600,
        chess.QUEEN: 900,
        chess.KING: 0,
    }
    return values.get(piece_type, 0)


def _is_center_square(square: int) -> bool:
    return square in {chess.D4, chess.E4, chess.D5, chess.E5}


def _safe_san(board: chess.Board, move: chess.Move) -> str:
    try:
        return board.san(move)
    except Exception:
        return ""


def _move_features(
    board: chess.Board,
    move: chess.Move,
    phase: str
) -> Dict[str, Any]:
    piece = board.piece_at(move.from_square)
    target_piece = board.piece_at(move.to_square)

    piece_type = piece.piece_type if piece is not None else None
    target_piece_type = target_piece.piece_type if target_piece is not None else None

    capture = board.is_capture(move)
    check = board.gives_check(move)
    castle = board.is_castling(move)
    promotion = move.promotion is not None
    center = _is_center_square(move.to_square)

    development = (
        phase == "opening"
        and piece_type in (chess.KNIGHT, chess.BISHOP)
        and move.from_square in {
            chess.B1, chess.G1, chess.C1, chess.F1,
            chess.B8, chess.G8, chess.C8, chess.F8,
        }
    )

    king_activity = (
        phase == "endgame"
        and piece_type == chess.KING
    )

    quiet = not capture and not check and not castle and not promotion

    return {
        "piece_type": piece_type,
        "target_piece_type": target_piece_type,
        "capture": capture,
        "check": check,
        "castle": castle,
        "promotion": promotion,
        "center": center,
        "development": development,
        "king_activity": king_activity,
        "quiet": quiet,
        "piece_name": chess.piece_name(piece_type) if piece_type else "",
    }


def _classify_move_quality(
    board: chess.Board,
    move: chess.Move,
    loss_cp: int,
    phase: str,
    is_best: bool = False
) -> str:
    features = _move_features(board, move, phase)

    piece_type = features["piece_type"]
    capture = features["capture"]
    check = features["check"]
    castle = features["castle"]
    promotion = features["promotion"]
    center = features["center"]
    development = features["development"]

    book_like = (
        phase == "opening"
        and loss_cp <= 8
        and (development or castle or center or promotion)
    )

    brilliant_like = (
        loss_cp <= 20
        and piece_type not in (None, chess.PAWN)
        and (check or castle or promotion or capture)
    )

    great_like = (
        loss_cp <= 12
        and (check or capture or castle or promotion or center)
    )

    if is_best:
        if book_like:
            return "Book(📖)"
        if brilliant_like:
            return "Brilliant (!!)"
        if great_like:
            return "Great (!)"
        return "Best(⭐)"

    if book_like:
        return "Book(📖)"
    if brilliant_like:
        return "Brilliant (!!)"
    if loss_cp <= 8:
        return "Excellent(👍)"
    if loss_cp <= 25:
        return "Good(✔)"
    if loss_cp <= 80:
        return "Inaccuracy(?!)"
    if loss_cp <= 180:
        return "Mistake(?)"
    if loss_cp <= 350:
        return "Miss(❌)"
    return "Blunder(??)"


def _tactical_profile(
    board: chess.Board,
    move: chess.Move
) -> Dict[str, bool]:
    piece = board.piece_at(move.from_square)
    target_piece = board.piece_at(move.to_square)
    piece_value = _move_piece_value(piece.piece_type) if piece else 0
    target_value = _move_piece_value(target_piece.piece_type) if target_piece else 0

    moved_board = board.copy()
    try:
        moved_board.push(move)
    except Exception:
        return {
            "sacrifice_like": False,
            "creates_major_threat": False,
        }

    opponent_color = not board.turn
    attacked_major_piece = False

    for square, attacked_piece in moved_board.piece_map().items():
        if attacked_piece.color != opponent_color:
            continue
        if _move_piece_value(attacked_piece.piece_type) < _move_piece_value(chess.ROOK):
            continue
        if not moved_board.is_attacked_by(board.turn, square):
            continue
        if board.is_attacked_by(board.turn, square):
            continue
        attacked_major_piece = True
        break

    sacrifice_like = (
        piece is not None
        and piece.piece_type != chess.PAWN
        and board.is_capture(move)
        and target_value < piece_value
    )

    return {
        "sacrifice_like": sacrifice_like,
        "creates_major_threat": attacked_major_piece,
    }


def _classify_move_quality(
    board: chess.Board,
    move: chess.Move,
    loss_cp: int,
    phase: str,
    is_best: bool = False,
    engine_rank: Optional[int] = None
) -> str:
    features = _move_features(board, move, phase)
    tactical_profile = _tactical_profile(board, move)

    piece_type = features["piece_type"]
    capture = features["capture"]
    check = features["check"]
    castle = features["castle"]
    promotion = features["promotion"]
    center = features["center"]
    development = features["development"]

    forcing = check or capture or promotion
    tactical_resource = (
        forcing
        or tactical_profile["creates_major_threat"]
        or tactical_profile["sacrifice_like"]
    )
    natural_opening_move = (
        phase == "opening"
        and (development or castle or center)
        and not tactical_profile["sacrifice_like"]
    )
    non_obvious = (
        tactical_profile["sacrifice_like"]
        or tactical_profile["creates_major_threat"]
        or (features["quiet"] and not natural_opening_move)
        or (
            piece_type not in (None, chess.PAWN)
            and forcing
            and not _is_center_square(move.to_square)
        )
    )
    difficult = (
        non_obvious
        and tactical_resource
        and not natural_opening_move
    )
    engine_approves_strongly = loss_cp <= 8 and (
        is_best
        or engine_rank in (1, 2)
        or engine_rank is None
    )

    if (
        difficult
        and tactical_resource
        and non_obvious
        and engine_approves_strongly
    ):
        return "Brilliant"

    if loss_cp <= 12 and (
        engine_rank in (1, 2)
        or forcing
        or tactical_profile["creates_major_threat"]
    ):
        return "Great"

    if is_best or engine_rank == 1:
        return "Best"

    if loss_cp <= 15:
        return "Excellent"
    if loss_cp <= 40:
        return "Good"
    if loss_cp <= 75:
        return "Interesting"
    if loss_cp <= 120:
        return "Dubious"
    if loss_cp <= 200:
        return "Inaccuracy"
    if loss_cp <= 450:
        return "Mistake"
    return "Blunder"


def _move_reason_lines(
    board: chess.Board,
    move: chess.Move,
    phase: str
) -> List[str]:
    features = _move_features(board, move, phase)
    lines: List[str] = []

    if features["castle"]:
        lines.append("It improves king safety and connects the rooks.")
    if features["check"]:
        lines.append("It is forcing, so the opponent must answer the check.")
    if features["capture"]:
        lines.append("It wins or trades material immediately.")
    if features["promotion"]:
        lines.append("It creates a new major piece and changes the game fast.")

    if phase == "opening":
        if features["development"]:
            lines.append("It develops a minor piece instead of wasting time.")
        if features["center"]:
            lines.append("It fights for the center, which controls the position.")
        if not lines:
            lines.append("It improves development or prepares a strong follow-up.")
    elif phase == "middlegame":
        if features["quiet"]:
            lines.append("It improves piece activity without creating weaknesses.")
        if features["center"]:
            lines.append("Central squares stay important for tactics and mobility.")
        if not lines:
            lines.append("It keeps pressure while preserving flexibility.")
    else:
        if features["king_activity"]:
            lines.append("In the endgame, the king becomes an active piece.")
        if features["center"]:
            lines.append("Centralization matters more in the endgame.")
        if not lines:
            lines.append("It improves king activity, rook activity, or pawn support.")

    return lines[:4]


def _pattern_tips(
    board: chess.Board,
    move: chess.Move,
    phase: str,
    player_model: PlayerModel
) -> List[str]:
    features = _move_features(board, move, phase)
    style = ""
    if player_model.user_profile is not None:
        style = str(player_model.user_profile.get("style_name", "")).strip()

    tips: List[str] = []

    if features["check"] or features["capture"]:
        tips.append("Scan forcing moves first: checks, captures, and direct threats.")
    else:
        tips.append("If nothing tactical exists, choose the move that improves your worst piece.")

    if phase == "opening":
        tips.append("In the opening, ask whether the move develops a piece, castles, or claims the center.")
    elif phase == "middlegame":
        tips.append("In the middlegame, look for moves that force a reply or improve piece activity.")
    else:
        tips.append("In the endgame, activate the king and push passed pawns.")

    if style in {"Aggressive", "Tactical"}:
        tips.append("Your style can stay sharp, but here the best move may be the quiet one that keeps the edge.")
    elif style in {"Positional", "Calm"}:
        tips.append("Your style fits this kind of position when you choose the move that increases activity without creating holes.")

    return tips[:4]


def get_moves_data(
    board: chess.Board,
    user_move: chess.Move,
    engine: chess.engine.SimpleEngine,
    player_model: PlayerModel
) -> Dict[str, Any]:
    phase = _board_phase(board)
    turn = board.turn
    analysis_depth = max(18, player_model.get_analysis_depth())
    best_move_rank = None

    try:
        info = engine.analyse(
            board,
            chess.engine.Limit(depth=analysis_depth),
            multipv=12
        )
    except Exception:
        return {
            "phase": phase,
            "best_move": None,
            "best_san": "",
            "user_rank": best_move_rank,
            "best_label": "Best(⭐)",
            "best_score_cp": 0,
            "user_move": user_move,
            "user_san": _safe_san(board, user_move),
            "user_label": "Unknown",
            "user_score_cp": 0,
            "loss_cp": 0,
            "best_reasons": [],
            "pattern_tips": [],
            "user_engine_data": _build_engine_data(board, user_move, 0, phase),
            "best_engine_data": {},
            "summary_text": "Could not evaluate this position.",
        }

    if not info or "pv" not in info[0] or not info[0]["pv"]:
        return {
            "phase": phase,
            "best_move": None,
            "best_san": "",
            "best_label": "Best(⭐)",
            "best_score_cp": 0,
            "user_move": user_move,
            "user_san": _safe_san(board, user_move),
            "user_label": "Unknown",
            "user_score_cp": 0,
            "loss_cp": 0,
            "best_reasons": [],
            "pattern_tips": [],
            "user_engine_data": _build_engine_data(board, user_move, 0, phase),
            "best_engine_data": {},
            "summary_text": "Could not evaluate this position.",
        }

    best_move_rank = None

    for idx, line in enumerate(info):
        pv = line.get("pv")

        if not pv:
            continue

        if pv[0] == user_move:
            best_move_rank = idx + 1
            break

    best_move = info[0]["pv"][0]
    best_line = info[0]["pv"][:6]

    try:
        user_board = board.copy()
        user_board.push(user_move)
        user_line_info = engine.analyse(
            user_board,
            chess.engine.Limit(depth=analysis_depth),
            multipv=1
        )
        user_line = [user_move] + user_line_info.get("pv", [])[:5]
    except Exception:
        user_line = [user_move]

    try:
        best_board = board.copy()
        best_board.push(best_move)
        best_after = engine.analyse(
            best_board,
            chess.engine.Limit(depth=analysis_depth),
            multipv=1
        )
        best_score_cp = _score_to_cp_for_turn(best_after["score"], turn)
    except Exception:
        best_score_cp = 0

    try:
        user_board = board.copy()
        user_board.push(user_move)
        user_after = engine.analyse(
            user_board,
            chess.engine.Limit(depth=analysis_depth),
            multipv=1
        )
        user_score_cp = _score_to_cp_for_turn(user_after["score"], turn)
    except Exception:
        user_score_cp = -10000

    loss_cp = max(0, best_score_cp - user_score_cp)

    best_san = _safe_san(board, best_move)
    user_san = _safe_san(board, user_move)

    best_label = _classify_move_quality(
        board=board,
        move=best_move,
        loss_cp=0,
        phase=phase,
        is_best=True,
        engine_rank=1
    )

    user_label = _classify_move_quality(
        board=board,
        move=user_move,
        loss_cp=loss_cp,
        phase=phase,
        is_best=False,
        engine_rank=best_move_rank
    )

    user_engine_data = _build_engine_data(
        board,
        user_move,
        loss_cp,
        phase
    )

    best_engine_data = _build_engine_data(
        board,
        best_move,
        0,
        phase
    )

    best_reasons = _move_reason_lines(
        board,
        best_move,
        phase
    )

    pattern_tips = _pattern_tips(
        board,
        best_move,
        phase,
        player_model
    )

    return {
        "phase": phase,
        "best_move": best_move,
        "best_san": best_san,
        "best_line": best_line,
        "user_line": user_line,
        "user_rank": best_move_rank,
        "best_label": best_label,
        "best_score_cp": best_score_cp,
        "user_move": user_move,
        "user_san": user_san,
        "user_label": user_label,
        "user_score_cp": user_score_cp,
        "loss_cp": loss_cp,
        "best_reasons": best_reasons,
        "pattern_tips": pattern_tips,
        "user_engine_data": user_engine_data,
        "best_engine_data": best_engine_data,
        "summary_text": (
            f"Stockfish prefers {best_san} over {user_san} by about {loss_cp} centipawns."
        ),
    }

def _line_to_san(board, line):
    temp = board.copy()
    result = []

    for move in line:
        try:
            result.append(temp.san(move))
            temp.push(move)
        except:
            break

    return result

def _describe_rank(rank):
    if rank == 1:
        return "You found the best move."

    if rank == 2:
        return "You found Stockfish's second choice."

    if rank == 3:
        return "You found Stockfish's third choice."

    if rank is None:
        return "Your move was outside Stockfish's top candidates."

    return f"Your move ranked #{rank}."

def _continuation_text(board, line):
    temp = board.copy()

    result = []

    for move in line[:4]:
        result.append(temp.san(move))
        temp.push(move)

    return " → ".join(result)

def _what_was_missed(
    board,
    best_move,
    user_move
):
    if board.gives_check(best_move) and not board.gives_check(user_move):
        return "You missed a forcing check."

    if board.is_capture(best_move) and not board.is_capture(user_move):
        return "You missed an immediate tactical capture."

    if board.is_castling(best_move) and not board.is_castling(user_move):
        return "You delayed king safety."

    return "You missed the strongest continuation."

def build_coach_explanation(
    board: chess.Board,
    moves_data: Dict[str, Any],
    player_model: PlayerModel
) -> str:
    best_san = _line_to_san(
        board,
        moves_data["best_line"]
    )
    user_san = _line_to_san(
        board,
        moves_data["user_line"]
    )
    best_label = moves_data.get("best_label", "Best(⭐)")
    user_label = moves_data.get("user_label", "Unknown")
    loss_cp = int(moves_data.get("loss_cp", 0))
    phase = moves_data.get("phase", "middlegame")

    if loss_cp <= 25:
        severity = "Practically equal"

    elif loss_cp <= 80:
        severity = "Small inaccuracy"

    elif loss_cp <= 180:
        severity = "Noticeable mistake"

    elif loss_cp <= 350:
        severity = "Serious mistake"

    else:
        severity = "Game-changing blunder"

    style = ""
    if player_model.user_profile is not None:
        style = str(player_model.user_profile.get("style_name", "")).strip()

    lines: List[str] = []

    if best_san and user_san and best_san == user_san:
        lines.append(f"You found the engine move: {best_san} — {best_label}.")
        lines.append("The lesson here is not the move itself, but why this position rewards it.")
    else:
        lines.append(f"Stockfish move: {best_san} — {best_label}")
        lines.append(f"Your move: {user_san} — {user_label}")
        lines.append(f"Severity: {severity}")

    lines.append("")

    engine_plan = _continuation_text(
        board,
        moves_data["best_line"]
    )

    user_plan = _continuation_text(
        board,
        moves_data["user_line"]
    )

    lines.append("")
    lines.append("Engine continuation:")
    lines.append(engine_plan)

    lines.append("")
    lines.append("Your continuation:")
    lines.append(user_plan)
    
    lines.append("")
    lines.append("How to find this kind of move yourself:")
    for tip in moves_data.get("pattern_tips", [])[:4]:
        lines.append(f"- {tip}")

    missed_text = _what_was_missed(
        board,
        moves_data["best_move"],
        moves_data["user_move"]
    )

    lines.append("")
    lines.append("What you missed:")
    lines.append(missed_text)

    if style:
        lines.append("")
        lines.append(f"Your current style: {style}")
        if style in {"Aggressive", "Tactical"} and phase == "opening":
            lines.append("- Here, the strong move is not another attack; it is the move that finishes development or secures the king.")
        elif style in {"Positional", "Calm"} and phase == "middlegame":
            lines.append("- Here, the strongest move is usually the one that creates a concrete threat, not just a small improvement.")

    return "\n".join(lines)


def _format_engine_rank(rank: Optional[int]) -> str:
    if rank is None:
        return "Outside top 12"
    return f"#{rank}"


def _coach_continuation_text(
    board: chess.Board,
    line: List[chess.Move]
) -> str:
    san_line = _line_to_san(board, line or [])
    if not san_line:
        return "No reliable continuation available."
    return " → ".join(san_line)


def _why_stockfish_preferred(
    board: chess.Board,
    best_move: Optional[chess.Move],
    phase: str
) -> str:
    if best_move is None:
        return "Stockfish could not provide a stable preferred move from this position."

    features = _move_features(board, best_move, phase)
    tactical_profile = _tactical_profile(board, best_move)

    if features["check"]:
        return "Stockfish preferred it because check is forcing: the opponent must answer before making their own plan."
    if features["capture"]:
        return "Stockfish preferred it because it resolves the position concretely instead of allowing the tension to drift."
    if tactical_profile["creates_major_threat"]:
        return "Stockfish preferred it because the move creates a direct threat against a major piece."
    if tactical_profile["sacrifice_like"]:
        return "Stockfish preferred it because the material investment is backed by a concrete tactical resource."
    if features["castle"]:
        return "Stockfish preferred it because king safety comes before ambition when the position can open quickly."
    if phase == "opening" and features["development"]:
        return "Stockfish preferred it because development gives every later tactic more force."
    if phase == "endgame" and features["king_activity"]:
        return "Stockfish preferred it because active kings decide endgames more often than passive defense."
    return "Stockfish preferred it because it improves the position while keeping the opponent's replies under control."


def _missed_idea_lines(
    board: chess.Board,
    best_move: Optional[chess.Move],
    user_move: chess.Move,
    phase: str
) -> List[str]:
    if best_move is None:
        return [
            "Tactical idea: No stable engine tactic was available to explain.",
            "Strategic idea: Re-check the position once the board is detected reliably.",
            "King safety issue: Not enough engine data to judge.",
            "Endgame issue: Not enough engine data to judge.",
            "Development issue: Not enough engine data to judge.",
        ]

    best_features = _move_features(board, best_move, phase)
    user_features = _move_features(board, user_move, phase)
    tactical_profile = _tactical_profile(board, best_move)

    if best_features["check"] and not user_features["check"]:
        tactical = "Tactical idea: you missed the forcing check, which should be examined before quiet moves."
    elif best_features["capture"] and not user_features["capture"]:
        tactical = "Tactical idea: you missed the concrete capture, so the position stayed more complicated than it needed to."
    elif tactical_profile["creates_major_threat"]:
        tactical = "Tactical idea: the engine move creates a threat against a major piece, not just a one-move improvement."
    elif tactical_profile["sacrifice_like"]:
        tactical = "Tactical idea: the engine accepts material risk because the follow-up gives compensation."
    else:
        tactical = "Tactical idea: there was no obvious forcing blow, so the tactic was hidden inside move order and piece activity."

    if phase == "opening":
        strategic = "Strategic idea: the priority is building a position where all pieces can join the fight."
    elif phase == "endgame":
        strategic = "Strategic idea: the priority is activity, especially king activity and pawn targets."
    else:
        strategic = "Strategic idea: the engine move improves coordination while limiting the opponent's counterplay."

    if best_features["castle"] and not user_features["castle"]:
        king_safety = "King safety issue: castling was the improvement; delaying it lets tactics against your king appear."
    elif best_features["check"]:
        king_safety = "King safety issue: the opponent's king could be forced, so their safety mattered more than slow improvement."
    else:
        king_safety = "King safety issue: not the main weakness, but always ask whether either king is vulnerable before choosing a plan."

    if phase == "endgame":
        if best_features["king_activity"]:
            endgame = "Endgame issue: the king needed to become a fighting piece."
        else:
            endgame = "Endgame issue: the move keeps activity and pawn structure coordinated."
    else:
        endgame = "Endgame issue: not the current phase, but the same habit applies later: activate before defending passively."

    if phase == "opening":
        if best_features["development"]:
            development = "Development issue: the engine move brings a piece into the game instead of spending a tempo on the edge."
        else:
            development = "Development issue: the move supports development, king safety, or central control."
    else:
        development = "Development issue: past the opening, undeveloped or passive pieces still become tactical liabilities."

    return [
        tactical,
        strategic,
        king_safety,
        endgame,
        development,
    ]


def _thinking_process_lines(
    board: chess.Board,
    best_move: Optional[chess.Move],
    phase: str
) -> List[str]:
    best_san = _safe_san(board, best_move) if best_move else "the engine move"
    return [
        "1. Scan checks first, because forcing moves reduce the opponent's choices.",
        "2. Scan captures and threats next; ask what changes immediately after each candidate.",
        "3. Evaluate king safety for both sides before trusting a quiet move.",
        "4. Improve the worst piece or urgent phase need: development, activity, or endgame king position.",
        f"5. Compare candidates by one concrete line, then choose {best_san} if its idea survives the reply.",
    ]


def _style_feedback_lines(
    board: chess.Board,
    best_move: Optional[chess.Move],
    phase: str,
    player_model: PlayerModel
) -> List[str]:
    profile = player_model.user_profile or {}
    style = str(profile.get("style_name", "Balanced")).strip() or "Balanced"
    weights = player_model.get_identity_weights()

    if best_move is None:
        return [
            f"Your current style: {style}",
            "Fit: unclear because the engine did not return a stable move.",
        ]

    features = _move_features(board, best_move, phase)
    forcing = features["check"] or features["capture"] or features["promotion"]
    quiet_improver = features["quiet"] or features["castle"] or features["development"]

    if style in {"Aggressive", "Tactical", "Sharp"}:
        if forcing:
            fit = "Fit: this matches your natural style; the stronger version of you should calculate it before looking for quieter plans."
        else:
            fit = "Fit: this stretches your style; the stronger version of you keeps the attack alive by improving first."
    elif style in {"Positional", "Calm"}:
        if quiet_improver:
            fit = "Fit: this matches your style; the stronger version of you turns calm improvement into concrete pressure."
        else:
            fit = "Fit: this asks you to add tactical urgency when the position demands it."
    elif style == "Creative":
        fit = "Fit: this rewards your creativity, but only after the forcing-move checklist proves the idea works."
    else:
        fit = "Fit: this suits a balanced style: calculate the forcing line, then choose the cleanest positional improvement."

    trait_note = (
        f"PlayerModel snapshot: calculation {int(weights['calculation'])}, "
        f"tactical preference {int(weights['tactical_preference'])}, "
        f"positional {int(weights['positional'])}, risk {int(weights['risk'])}."
    )

    return [
        f"Your current style: {style}",
        fit,
        trait_note,
    ]


def _future_pattern(
    board: chess.Board,
    best_move: Optional[chess.Move],
    phase: str
) -> str:
    if best_move is None:
        return "When analysis is unstable, first verify the board state before trusting any lesson."

    features = _move_features(board, best_move, phase)
    tactical_profile = _tactical_profile(board, best_move)
    opponent_king_square = board.king(not board.turn)
    opponent_uncastled = opponent_king_square in {
        chess.E1, chess.E8, chess.D1, chess.D8, chess.F1, chess.F8
    }

    if opponent_uncastled and (features["check"] or tactical_profile["creates_major_threat"]):
        return "When your opponent's king is uncastled, forcing moves become more important than slow development."
    if features["check"] or features["capture"]:
        return "When a forcing move exists, examine it before improving a piece; forcing moves tell you whether the tactic is real."
    if features["castle"]:
        return "When the center may open, secure your king before starting a side quest. The board has enough drama already."
    if phase == "opening" and features["development"]:
        return "When you are still developing, every useful tempo should bring a new piece into the game or fight for the center."
    if phase == "endgame" and features["king_activity"]:
        return "In endgames, the king is not cargo; it is a piece, and active kings create winning chances."
    if tactical_profile["creates_major_threat"]:
        return "A quiet move can be tactical if it creates a threat the opponent cannot comfortably meet."
    return "When no tactic is obvious, improve the piece with the least future and compare only moves that solve a real problem."


def build_coach_explanation(
    board: chess.Board,
    moves_data: Dict[str, Any],
    player_model: PlayerModel
) -> str:
    phase = moves_data.get("phase", "middlegame")
    best_move = moves_data.get("best_move")
    user_move = moves_data.get("user_move")
    user_san = moves_data.get("user_san") or _safe_san(board, user_move)
    user_label = moves_data.get("user_label", "Unknown")
    rank = moves_data.get("user_rank")
    loss_cp = int(moves_data.get("loss_cp", 0))

    lines: List[str] = []

    lines.append("SECTION 1")
    lines.append("Move Quality")
    lines.append("")
    lines.append(f"Your move: {user_san}")
    lines.append(f"Category: {user_label}")
    lines.append(f"Engine Rank: {_format_engine_rank(rank)}")
    lines.append(f"Evaluation Loss: {loss_cp} cp")

    lines.append("")
    lines.append("SECTION 2")
    lines.append("What You Missed")
    lines.append("")
    lines.append(_why_stockfish_preferred(board, best_move, phase))
    for idea in _missed_idea_lines(board, best_move, user_move, phase):
        lines.append(f"- {idea}")

    lines.append("")
    lines.append("SECTION 3")
    lines.append("Engine Continuation")
    lines.append("")
    lines.append(f"Best: {_coach_continuation_text(board, moves_data.get('best_line', []))}")
    lines.append(f"User: {_coach_continuation_text(board, moves_data.get('user_line', []))}")

    lines.append("")
    lines.append("SECTION 4")
    lines.append("Thinking Process")
    lines.append("")
    for step in _thinking_process_lines(board, best_move, phase):
        lines.append(step)

    lines.append("")
    lines.append("SECTION 5")
    lines.append("Style Feedback")
    lines.append("")
    for style_line in _style_feedback_lines(board, best_move, phase, player_model):
        lines.append(style_line)

    lines.append("")
    lines.append("SECTION 6")
    lines.append("Future Pattern")
    lines.append("")
    lines.append(_future_pattern(board, best_move, phase))

    return "\n".join(lines)


def find_played_move(
    previous_board: chess.Board,
    current_board: chess.Board
) -> Optional[chess.Move]:

    for move in previous_board.legal_moves:
        test_board = previous_board.copy()
        test_board.push(move)

        if test_board.board_fen() == current_board.board_fen():
            return move

    return None

def start_coach_mode(
    model,
    engine,
    ui_callback=None,
    bus=None,
    is_running=None
):

    pending_player_move = None

    def receive_player_move(move_text):
        nonlocal pending_player_move
        pending_player_move = move_text

    if bus is not None:
        bus.player_move_submitted.connect(
            receive_player_move
        )

    tracker = BoardTracker(model)

    player_model = PlayerModel()
    player_model.load_user_profile()
    player_model.set_mode("coach")
    player_model.reset_opponent_profile()

    if is_running is None:
        is_running = lambda: True

    side_request_sent = False
    last_fen = None
    last_seen_fen = None
    last_turn_state = None
    last_suggested_fen = None

    def update_ui(move=None, evaluation=None, status_text=None):
        if ui_callback is None:
            return
        try:
            ui_callback(
                move=move,
                evaluation=evaluation,
                status_text=status_text
            )
        except Exception:
            pass

    while is_running():

        if not tracker.game_started:

            update_ui(
                status_text="Press Start Game"
            )

            continue
        
        position = tracker.get_position()

        if not position.get("board_found"):
            update_ui(status_text="Searching For Board...")
            time.sleep(0.1)
            continue

        if tracker.user_color is None:

            tracker.try_auto_detect_side()

            if tracker.user_color is None:

                update_ui(status_text="Choose White Or Black")

                if bus is not None and not side_request_sent:
                    try:
                        bus.choose_side_required.emit()
                        side_request_sent = True
                    except Exception:
                        pass

                time.sleep(0.1)
                continue

        side_request_sent = False

        fen = position.get("fen")
        current_turn = tracker.is_users_turn()
        move_source = position.get("move_source") or tracker.last_move_source

        if fen is None:
            time.sleep(0.05)
            continue

        if (
            last_seen_fen is not None
            and fen != last_seen_fen
        ):
            try:
                previous_board = chess.Board(last_seen_fen)
                current_board = chess.Board(fen)

                played_move = find_played_move(
                    previous_board,
                    current_board
                )

                if played_move is not None:
                    move_error = calculate_move_error(
                        previous_board,
                        played_move,
                        engine,
                        player_model
                    )

                    engine_data = _build_engine_data(
                        previous_board,
                        played_move,
                        move_error,
                        _board_phase(previous_board)
                    )

                    if move_source == "user" or (
                        move_source is None and last_turn_state is True and current_turn is False
                    ):
                        player_model.record_user_move(
                            previous_board,
                            played_move,
                            engine_data
                        )
                    elif move_source == "opponent" or (
                        move_source is None and last_turn_state is False and current_turn is True
                    ):
                        player_model.record_opponent_move(
                            previous_board,
                            played_move,
                            {
                                "move_error": move_error,
                                "is_capture": previous_board.is_capture(played_move),
                                "gives_check": previous_board.gives_check(played_move),
                            }
                        )

                    last_suggested_fen = None

            except Exception:
                pass

        if not current_turn:
            update_ui(status_text="Waiting For Opponent Move...")
            last_seen_fen = fen
            last_turn_state = current_turn
            time.sleep(0.08)
            continue

        current_board_key = chess.Board(fen).board_fen()

        if current_board_key == last_suggested_fen:

            try:
                update_ui(
                    move="Thinking",
                    status_text="Analysing Board..."
                )

                board_obj = chess.Board(fen)

                info = engine.analyse(
                    board_obj,
                    chess.engine.Limit(depth=20)
                )

                score_obj = info["score"].white()
                evaluation = _score_to_eval_text(score_obj)

                update_ui(status_text="Building Candidates...")

                candidate_moves = get_candidate_moves(
                    board_obj,
                    engine,
                    depth=player_model.get_analysis_depth(),
                    multipv=12
                )

                if not candidate_moves:
                    update_ui(
                        status_text="No Candidate Moves Found"
                    )
                    last_seen_fen = fen
                    last_turn_state = current_turn
                    last_suggested_fen = chess.Board(fen).board_fen()
                    time.sleep(0.08)
                    continue

                update_ui(status_text="Matching Your Style...")

                selected = player_model.select_move(
                    board_obj,
                    candidate_moves
                )

                if selected is None:
                    update_ui(
                        status_text="No Move Selected"
                    )
                    last_seen_fen = fen
                    last_turn_state = current_turn
                    last_suggested_fen = chess.Board(fen).board_fen()
                    time.sleep(0.08)
                    continue

                suggested_move = board_obj.san(selected["move"])

                update_ui(
                    move=suggested_move,
                    evaluation=evaluation,
                    status_text="Move Ready"
                )

                last_fen = fen
                last_seen_fen = fen
                last_turn_state = current_turn
                last_suggested_fen = chess.Board(fen).board_fen()

                suggested_engine_move = selected["move"]

                update_ui(
                    move=suggested_move,
                    evaluation=evaluation,
                    status_text="Enter Your Move"
                )

                pending_player_move = None

                waiting_for_user_move = True

                while is_running() and waiting_for_user_move:

                    position = tracker.get_position()

                    if position.get("fen") != fen:
                        waiting_for_user_move = False
                        break

                    if pending_player_move is not None:
                        waiting_for_user_move = False
                        break

                    time.sleep(0.03)

                user_move_text = pending_player_move

                try:
                    user_move = board_obj.parse_san(user_move_text)
                except Exception:
                    update_ui(status_text="Invalid Move")
                    continue

                moves_data = get_moves_data(
                    board_obj,
                    user_move,
                    engine,
                    player_model
                )

                explanation_text = build_coach_explanation(
                    board_obj,
                    moves_data,
                    player_model
                )

                player_model.record_user_move(
                    board_obj,
                    user_move,
                    moves_data["user_engine_data"]
                )

                update_ui(
                    evaluation=_score_to_eval_text(
                        info["score"],
                        board_obj.turn
                    ),
                    status_text=explanation_text
                )

            except Exception:
                time.sleep(0.08)
                continue
