import mss
import cv2
import chess
import numpy as np
import json
import pytesseract
from collections import (
    deque,
    Counter
)

class BoardTracker:

    def __init__(self, model):

        self.model = model

        self.BOARD_SIZE = 480

        self.board_history = deque(
            maxlen=5
        )

        self.freeze_frames = 8
        
        self.sct = mss.MSS()

        self.monitor = (
            self.sct.monitors[1]
        )

        self.current_board = None
        
        self.previous_board = None

        self.side_to_move = "w"

        self.castling_rights = "KQkq"

        self.en_passant = "-"

        self.halfmove_clock = 0

        self.fullmove_number = 1

        self.board_state = None

        self.prev_frame = None

        self.freeze_counter = 0

        self.user_color = None
        
        self.opponent_color = None

        self.last_move_source = None

        self.move_history = deque(maxlen=20)

        self.player_detection_done = False

        self.user_position = None

        self.game_started = False

        self.freeze_counter = 0

        self.prev_frame = None

        self.board_history.clear()

    def start_game(self):

        self.game_started = True

        self.freeze_counter = 0

        self.prev_frame = None

        self.board_history.clear()
        
        self.player_detection_done = False

        self.user_color = None
        
        self.opponent_color = None

        self.last_move_source = None

        self.user_position = None

        self.board_state = None
        
        self.current_board = None
        
        self.previous_board = None

        self.move_history.clear()

    def is_users_turn(self):

        if (
            self.board_state is None
            or
            self.user_color is None
        ):
            return False

        current_turn = (
            "w"
            if self.board_state.turn
            else "b"
        )

        return current_turn == self.user_color

    def detect_orientation(self, board):
        # temporary safe fallback (until UI detection added later)
        # assumes white is bottom by default

        return "white_bottom"

    def set_user_color(self, color):
        if color not in ["w", "b"]:
            raise ValueError("color must be 'w' or 'b'")

        self.user_color = color
        self.opponent_color = "b" if color == "w" else "w"

    def determine_user_color_from_board(
        self,
        board
    ):
        if self.user_position is None:
            return

        top_white = sum(
            piece is not None and piece.isupper()
            for piece in board[0]
        )

        top_black = sum(
            piece is not None and piece.islower()
            for piece in board[0]
        )

        bottom_white = sum(
            piece is not None and piece.isupper()
            for piece in board[7]
        )

        bottom_black = sum(
            piece is not None and piece.islower()
            for piece in board[7]
        )

        if self.user_position == "bottom":

            if bottom_white > bottom_black:
                self.user_color = "w"
                self.opponent_color = "b"
            else:
                self.user_color = "b"
                self.opponent_color = "w"

        elif self.user_position == "top":

            if top_white > top_black:
                self.user_color = "w"
                self.opponent_color = "b"
            else:
                self.user_color = "b"
                self.opponent_color = "w"

    def try_auto_detect_side(self):

        if self.user_color is not None:
            return

        if self.user_position is None:
            return

        if self.current_board is None:
            return

        top_row = self.current_board[0]
        bottom_row = self.current_board[7]

        top_white = sum(
            p is not None and p.isupper()
            for p in top_row
        )

        top_black = sum(
            p is not None and p.islower()
            for p in top_row
        )

        bottom_white = sum(
            p is not None and p.isupper()
            for p in bottom_row
        )

        bottom_black = sum(
            p is not None and p.islower()
            for p in bottom_row
        )
        
        if (
            top_white + top_black != 8 or
            bottom_white + bottom_black != 8
        ):
            return

        self.determine_user_color_from_board(
            self.current_board
        )

        self.player_detection_done = (
            self.user_color is not None
        )

    def detect_user_side(self, frame, board_box):

        try:

            with open("player_profile.json", "r") as f:
                profile = json.load(f)

            username = profile["name"].lower()

        except:
            return

        x1, y1, x2, y2 = map(int, board_box)

        top_region = frame[
            max(0, y1 - 80):y1,
            x1:x2
        ]

        bottom_region = frame[
            y2:min(frame.shape[0], y2 + 80),
            x1:x2
        ]

        top_text = pytesseract.image_to_string(
            top_region
        ).lower()

        bottom_text = pytesseract.image_to_string(
            bottom_region
        ).lower()

        if username in bottom_text:
            self.user_position = "bottom"

        elif username in top_text:
            self.user_position = "top"

    def get_turn(self):
        if self.board_state is None:
            return None
        return "w" if self.board_state.turn else "b"

    def infer_move_source(self):
        if self.board_state is None:
            return None

        last_moved_side = "b" if self.board_state.turn else "w"

        if self.user_color is None:
            return None

        if last_moved_side == self.user_color:
            return "user"

        return "opponent"

    def get_active_context(self):
        return {
            "fen": self.board_state.fen() if self.board_state else None,
            "turn": self.get_turn(),
            "user_color": self.user_color,
            "engine_side": self.user_color if self.board_state and self.board_state.turn == (self.user_color == "w") else self.opponent_color,
            "last_move_source": self.last_move_source
        }
        
    def is_valid_board(self, board):

        if board is None:
            return False

        piece_count = 0

        white_kings = 0
        black_kings = 0

        for row in board:

            for cell in row:

                if cell is not None:

                    piece_count += 1

                    if cell == "K":
                        white_kings += 1

                    elif cell == "k":
                        black_kings += 1

        if piece_count < 2 or piece_count > 32:
            return False

        if white_kings != 1:
            return False

        if black_kings != 1:
            return False

        return True

    def is_ui_movement(self, frame, prev_frame):

        if prev_frame is None:
            return False

        diff = cv2.absdiff(frame, prev_frame)
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5,5), 0)

        _, thresh = cv2.threshold(blur, 25, 255, cv2.THRESH_BINARY)

        motion = np.sum(thresh > 0)

        # tune thresholds
        if motion > 50000:
            return True

        return False

    def get_win_mode_context(self):
        if self.board_state is None:
            return None

        return {
            "fen": self.board_state.fen(),
            "turn": self.get_turn(),
            "user_color": self.user_color,
            "last_move_source": self.last_move_source,
            "move_history": list(self.move_history)
        }

    def normalize_board(self, board):

        if self.detect_orientation(board) == "black_bottom":

            # flip vertically + horizontally
            return [
                list(reversed(row))
                for row in reversed(board)
            ]

        return board

    def is_new_game(self, board):

        empty_count = 0

        for row in board:
            for cell in row:
                if cell is None:
                    empty_count += 1

        if empty_count > 48:
            return True

        return False

    def get_board_box(self, frame):

        results = self.model(
            frame,
            verbose=False
        )[0]

        best_box = None
        best_conf = 0

        for box in results.boxes:

            cls = int(box.cls[0])

            label = results.names[cls]

            if label != "board":
                continue

            conf = float(box.conf[0])

            if conf > best_conf:

                best_conf = conf
                best_box = box.xyxy[0]

        return best_box

    # -------------------------
    # YOLO PIECE DETECTION
    # -------------------------
    def detect_pieces_yolo(self, warp):

        board = [
            [None for _ in range(8)]
            for _ in range(8)
        ]

        results = self.model(
            warp,
            verbose=False
        )[0]

        for box in results.boxes:
            
            if box == "board":
                continue
            
            conf = float(box.conf[0])

            if conf < 0.75:
                continue

            cls = int(box.cls[0])

            label = results.names[cls]

            x1, y1, x2, y2 = box.xyxy[0]

            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            sq = self.BOARD_SIZE // 8
            
            col = min(cx // sq, 7)
            row = min(cy // sq, 7)

            piece_map = {
                
                "white_pawn": "P",
                "white_knight": "N",
                "white_bishop": "B",
                "white_rook": "R",
                "white_queen": "Q",
                "white_king": "K",

                "black_pawn": "p",
                "black_knight": "n",
                "black_bishop": "b",
                "black_rook": "r",
                "black_queen": "q",
                "black_king": "k",
            }

            if label in piece_map:
                
                board[row][col] = piece_map[label]

        return board

    # -------------------------
    # BOARD STABILIZATION
    # -------------------------
    def stabilize_board(self, board):

        self.board_history.append(board)

        if len(self.board_history) < 3:
            return board

        stable = []

        for i in range(8):

            row = []

            for j in range(8):

                vals = [
                    b[i][j]
                    for b in self.board_history
                ]

                stable_val = Counter(vals).most_common(1)[0][0]

                row.append(stable_val)

            stable.append(row)

        return stable

    # -------------------------
    # FEN BUILDER
    # -------------------------
    def board_to_fen(self, board):

        rows = []

        for row in board:

            empty = 0

            fen = ""

            for cell in row:

                if cell is None:

                    empty += 1

                else:

                    if empty:

                        fen += str(empty)

                        empty = 0

                    fen += cell

            if empty:
                fen += str(empty)

            rows.append(fen)

        return "/".join(rows)

    def get_position(self):

        img = np.array(
            self.sct.grab(
                self.monitor
            )
        )

        frame = cv2.cvtColor(
            img,
            cv2.COLOR_BGRA2BGR
        )

        if self.freeze_counter > 0:
            self.freeze_counter -= 1
            return {
                "board_found": True,
                "fen": self.board_state.fen() if self.board_state else None,
                "frame": frame,
                "warp": None,
                "board": self.current_board,
                "move": None
            }

        if self.is_ui_movement(frame, self.prev_frame):
            self.freeze_counter = self.freeze_frames

        self.prev_frame = frame

        board_box = self.get_board_box(
            frame
        )

        if board_box is None:

            return {
                "board_found": False,
                "fen": None,
                "frame": frame,
                "warp": None,
                "board": None,
                "move": []
            }

        if (
            not self.player_detection_done
            and
            self.user_position is None
        ):
            self.detect_user_side(
                frame,
                board_box
            )

        x1, y1, x2, y2 = map(
            int,
            board_box
        )

        crop = frame[
            y1:y2,
            x1:x2
        ]

        warp = cv2.resize(
            crop,
            (
                self.BOARD_SIZE,
                self.BOARD_SIZE
            )
        )

        board = self.detect_pieces_yolo(warp)
        if (
            not self.player_detection_done
            and
            self.user_position is not None
        ):
            self.determine_user_color_from_board(
                board
            )
            
            if self.user_color is not None:
                self.player_detection_done = True
        board = self.normalize_board(board)
        board = self.stabilize_board(board)

        if (
            self.is_new_game(board)
            and
            self.board_state is not None
            and
            len(self.move_history) > 0
        ):
            self.player_detection_done = False

            self.user_color = None
            self.opponent_color = None
            self.board_state = None
            self.current_board = None
            self.previous_board = None
            self.freeze_counter = 0
            self.user_position = None
            self.last_move_source = None
            self.move_history.clear()

            return {
                "board_found": True,
                "fen": None,
                "user_color": self.user_color,
                "move_source": self.last_move_source,
                "turn": self.get_turn(),
                "frame": frame,
                "warp": warp,
                "board": board,
                "move": None
            }
        
        previous_move_count = len(self.move_history)

        self.previous_board = self.current_board
        
        self.current_board = [
            row[:]
            for row in board
        ]

        if self.board_state is None:

            if not self.build_initial_board_state(
                board
            ):

                return {
                    "board_found": True,
                    "fen": fen if self.board_state else None,
                    "move_source": self.last_move_source,
                    "user_color": self.user_color,
                    "turn": self.get_turn(),
                    "frame": frame,
                    "warp": warp,
                    "board": board,
                    "move": (
                        self.move_history[-1]
                        if len(self.move_history) > 0
                        else None
                    )
                }

        move_found = self.update_board_state(board)

        fen = self.board_state.fen() if self.board_state else None

        detected_move = None

        if len(self.move_history) > previous_move_count:
            detected_move = self.move_history[-1]

        if self.freeze_counter > 0:
            self.freeze_counter -= 1
        
            return {
                "board_found": True,
                "fen": fen if self.board_state else None,
                "move_source": self.last_move_source,
                "turn": self.get_turn(),
                "frame": frame,
                "warp": warp,
                "board": board,
                "move": (
                    self.move_history[-1]
                    if len(self.move_history) > 0
                    else None
                )
            }
        
        return {
            "board_found": True,
            "fen": fen if self.board_state else None,
            "move_source": self.last_move_source,
            "user_color": self.user_color,
            "turn": self.get_turn(),
            "frame": frame,
            "warp": warp,
            "board": board,
            "move": (
                self.move_history[-1]
                if len(self.move_history) > 0
                else None
            )
        }

    def build_initial_board_state(self, board):

        if not self.is_valid_board(board):
            return False

        piece_fen = self.board_to_fen(
            board
        )

        full_fen = (
            f"{piece_fen} "
            f"{self.side_to_move} "
            f"{self.castling_rights} "
            f"{self.en_passant} "
            f"{self.halfmove_clock} "
            f"{self.fullmove_number}"
        )

        try:

            self.board_state = chess.Board(
                full_fen
            )

            return True

        except:

            self.board_state = None

            return False

    def update_board_state(self, current_board):

        if not self.is_valid_board(current_board):
            return False

        if self.board_state is None:
            return False

        piece_fen = self.board_to_fen(
            current_board
        )

        legal_moves = list(
            self.board_state.legal_moves
        )

        for move in legal_moves:

            test_board = self.board_state.copy()

            test_board.push(move)

            future_fen = self.board_to_fen_from_board(
                test_board
            )

            if future_fen == piece_fen:

                if (
                    len(self.move_history) > 0
                    and
                    self.move_history[-1]["move"] == move.uci()
                ):
                    return False

                self.board_state.push(move)
                source = self.infer_move_source()
                self.last_move_source = source

                self.move_history.append({
                    "move": move.uci(),
                    "source": source
                })

                return True

        return False

    def board_to_fen_from_board(
        self,
        board_obj
    ):

        rows = []

        for rank in range(7, -1, -1):

            empty = 0

            row_fen = ""

            for file in range(8):

                piece = board_obj.piece_at(
                    chess.square(
                        file,
                        rank
                    )
                )

                if piece is None:

                    empty += 1

                else:

                    if empty:

                        row_fen += str(
                            empty
                        )

                        empty = 0

                    row_fen += piece.symbol()

            if empty:

                row_fen += str(
                    empty
                )

            rows.append(
                row_fen
            )

        return "/".join(rows)
