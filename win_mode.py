import chess
import chess.engine
import time
from board_system.board_tracker import BoardTracker
from game_intelligence.player_model import PlayerModel

def get_candidate_moves(
    board,
    engine,
    depth
):

    candidates = []

    info = engine.analyse(
        board,
        chess.engine.Limit(
            depth=depth
        ),
        multipv=8
    )

    for line in info:

        move = line["pv"][0]

        score_obj = (
            line["score"]
            .white()
        )

        if score_obj.is_mate():

            engine_score = 100

        else:

            engine_score = (
                score_obj.score(
                    mate_score=10000
                ) / 100.0
            )

        candidates.append({

            "move": move,

            "engine_score":
            engine_score,

            "is_capture":
            board.is_capture(move),

            "gives_check":
            board.gives_check(move),

            "is_promotion":
            move.promotion is not None,

            "is_castle":
            board.is_castling(move),

            "piece_type":
            (
                board.piece_at(
                    move.from_square
                ).piece_type

                if board.piece_at(
                    move.from_square
                )

                else None
            ),

            "raw_score":
            score_obj.score(
                mate_score=10000
            )
        })

    return candidates

def calculate_move_error(
    board,
    move,
    engine,
    player_model
):

    analysis_depth = (
        player_model.get_analysis_depth()
    )

    info = engine.analyse(
        board,
        chess.engine.Limit(
            depth=analysis_depth
        ),
        multipv=2
    )

    best_score = (
        info[0]["score"]
        .white()
        .score(
            mate_score=10000
        )
    )

    played_score = None

    for line in info:

        if line["pv"][0] == move:

            played_score = (
                line["score"]
                .white()
                .score(
                    mate_score=10000
                )
            )

            break

    if played_score is None:

        return 300

    return abs(
        best_score -
        played_score
    )

def find_played_move(
    previous_board,
    current_board
):

    for move in previous_board.legal_moves:

        test_board = (
            previous_board.copy()
        )

        test_board.push(move)

        if (
            test_board.board_fen()
            ==
            current_board.board_fen()
        ):

            return move

    return None

def start_win_mode(
    tracker,
    engine,
    ui_callback,
    bus,
    is_running
):
    
    side_request_sent = False
    last_fen = None
    last_seen_fen = None
    last_turn_state = None

    player_model = PlayerModel()

    player_model.load_user_profile()

    player_model.reset_opponent_profile()

    player_model.set_mode("win")

    def update_ui(
        move=None,
        evaluation=None,
        status_text=None
    ):

        if ui_callback is None:
            return

        try:

            ui_callback(
                move=move,
                evaluation=evaluation,
                status_text=status_text
            )

        except:
            pass

    while is_running():

        if not tracker.game_started:

            update_ui(
                status_text="Press Start Game"
            )

            continue

        position = tracker.get_position()

        fen = position["fen"]

        current_turn = (
            tracker.is_users_turn()
        )

        if not position["board_found"]:

            update_ui(
                status_text="Searching For Board..."
            )

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
        
        if fen is None:
            continue

        if (
            last_seen_fen is not None
            and
            fen != last_seen_fen
        ):
            try:

                if (
                    last_turn_state is False
                    and
                    current_turn is True
                ):

                    previous_board = chess.Board(
                        last_seen_fen
                    )

                    current_board = chess.Board(
                        fen
                    )

                    played_move = find_played_move(
                        previous_board,
                        current_board
                    )

                    if played_move:

                        move_error = (
                            calculate_move_error(
                                previous_board,
                                played_move,
                                engine,
                                player_model
                            )
                        )

                        player_model.record_opponent_move(
                            previous_board,
                            played_move,
                            {
                                "move_error": move_error,
                                "is_capture":
                                    previous_board.is_capture(
                                        played_move
                                    ),
                                "gives_check":
                                    previous_board.gives_check(
                                        played_move
                                    )
                            }
                        )

            except Exception:
                pass

        if not current_turn:

            update_ui(
                status_text="Waiting For Opponent Move..."
            )

            last_seen_fen = fen
            last_turn_state = current_turn

            continue
        
        if fen == last_fen:
            continue

        try:

            update_ui(
                move="Thinking",
                status_text="Analysing Board..."
            )

            board_obj = chess.Board(
                fen
            )

            info = engine.analyse(
                board_obj,
                chess.engine.Limit(
                    depth=11
                )
            )

            score_obj = (
                info["score"]
                .white()
            )

            if score_obj.is_mate():

                eval_value = (
                    10
                    if score_obj.mate() > 0
                    else -10
                )

            else:

                eval_value = (
                    score_obj.score()
                    / 100.0
                )

            update_ui(
                status_text="Building Candidates..."
            )

            analysis_depth = (
                player_model.get_analysis_depth()
            )

            candidate_moves = get_candidate_moves(
                board_obj,
                engine,
                analysis_depth
            )
            
            update_ui(
                status_text="Matching Your Style..."
            )

            selected = (
                player_model.select_move(
                    board_obj,
                    candidate_moves
                )
            )

            best_move = (
                board_obj.san(
                    selected["move"]
                )
            )

            if score_obj.is_mate():

                mate_moves = (
                    score_obj.mate()
                )

                if mate_moves > 0:

                    evaluation = (
                        f"Mate in {mate_moves}"
                    )

                else:

                    evaluation = (
                        f"Mated in {abs(mate_moves)}"
                    )

            else:

                evaluation = (
                    f"{eval_value:.2f}"
                )

            update_ui(
                move=best_move,
                evaluation=evaluation,
                status_text="Move Ready"
            )

            last_fen = fen
            
            last_seen_fen = fen

            last_turn_state = current_turn

        except Exception:

            continue
