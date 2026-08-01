import json
import os
import math
import chess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PROFILE_PATH = os.path.join(
    BASE_DIR,
    "..",
    "player_profile",
    "player_profile.json"
)


class PlayerModel:

    def __init__(self):

        self.user_profile = None
        self.opponent_profile = None
        self.smoothed_rating = 1100

        self.mode = "win"
        self.identity_lock = True

    def _clamp(self, value, low=0, high=100):
        return max(low, min(high, int(round(value))))

    def _ensure_profile_defaults(self):
        if self.user_profile is None:
            return

        defaults = {
            "name": "",
            "rating": 1100,
            "chesscom_username": "",

            "personality_name": "Wildcard",
            "style_name": "Wildcard",

            "intuition": 50,
            "calculation": 50,
            "attacking": 50,
            "positional": 50,
            "calm": 50,
            "emotional": 50,
            "playful": 50,
            "studious": 50,
            "confidence": 50,
            "risk": 50,

            "opening_aggression": 50,
            "opening_flexibility": 50,
            "sacrifice_tendency": 50,
            "piece_activity": 50,
            "king_attack": 50,
            "endgame_skill": 50,
            "exchange_preference": 50,
            "tactical_preference": 50,

            "games_analyzed": 0,
            "moves_analyzed": 0,

            "last_chesscom_sync": "",
            "opening_repertoire": {},
            "style_vector": {},

            "chesscom_analyzed_game_urls": [],
            "chesscom_analyzed_game_count": 0,
        }

        for key, value in defaults.items():
            self.user_profile.setdefault(key, value)

    def _ensure_opponent_defaults(self):
        if self.opponent_profile is None:
            self.reset_opponent_profile()
            return

        defaults = {
            "estimated_rating": 1100,
            "moves_seen": 0,
            "average_error": 0,
            "recent_errors": [],
            "confidence": 0,
            "aggression": 50,
            "tactical": 50,
            "positional": 50,
            "risk": 50,
        }

        for key, value in defaults.items():
            self.opponent_profile.setdefault(key, value)

    def set_mode(self, mode: str):
        if mode not in ["win", "coach"]:
            raise ValueError("mode must be 'win' or 'coach'")
        self.mode = mode

    def load_user_profile(self):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as file:
                self.user_profile = json.load(file)
        except Exception:
            self.user_profile = {}

        self._ensure_profile_defaults()
        return self.user_profile

    def save_user_profile(self):
        if self.user_profile is None:
            return

        self._ensure_profile_defaults()

        os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)

        with open(PROFILE_PATH, "w", encoding="utf-8") as file:
            json.dump(self.user_profile, file, indent=4)

    def reset_opponent_profile(self):
        self.opponent_profile = {
            "estimated_rating": 1100,
            "moves_seen": 0,
            "average_error": 0,
            "recent_errors": [],
            "confidence": 0,
            "aggression": 50,
            "tactical": 50,
            "positional": 50,
            "risk": 50,
        }

    def get_identity_weights(self):
        self._ensure_profile_defaults()

        p = self.user_profile

        return {
            "intuition": float(p.get("intuition", 50)),
            "calculation": float(p.get("calculation", 50)),
            "attacking": float(p.get("attacking", 50)),
            "positional": float(p.get("positional", 50)),
            "calm": float(p.get("calm", 50)),
            "emotional": float(p.get("emotional", 50)),
            "playful": float(p.get("playful", 50)),
            "studious": float(p.get("studious", 50)),
            "confidence": float(p.get("confidence", 50)),
            "risk": float(p.get("risk", 50)),
            "opening_aggression": float(p.get("opening_aggression", 50)),
            "opening_flexibility": float(p.get("opening_flexibility", 50)),
            "sacrifice_tendency": float(p.get("sacrifice_tendency", 50)),
            "piece_activity": float(p.get("piece_activity", 50)),
            "king_attack": float(p.get("king_attack", 50)),
            "endgame_skill": float(p.get("endgame_skill", 50)),
            "exchange_preference": float(p.get("exchange_preference", 50)),
            "tactical_preference": float(p.get("tactical_preference", 50)),
        }

    def update_style_name(self):
        if self.user_profile is None:
            return

        self._ensure_profile_defaults()

        attack = float(self.user_profile.get("attacking", 50))
        positional = float(self.user_profile.get("positional", 50))
        calc = float(self.user_profile.get("calculation", 50))
        intuition = float(self.user_profile.get("intuition", 50))
        tactical_pref = float(self.user_profile.get("tactical_preference", 50))
        endgame = float(self.user_profile.get("endgame_skill", 50))
        opening = float(self.user_profile.get("opening_aggression", 50))
        calm = float(self.user_profile.get("calm", 50))

        if tactical_pref >= attack and tactical_pref >= positional and tactical_pref >= endgame:
            style = "Tactical"
        elif positional >= attack and positional >= tactical_pref:
            style = "Positional"
        elif attack >= positional and attack >= tactical_pref:
            style = "Aggressive"
        elif opening >= 65:
            style = "Sharp"
        elif calm >= 65:
            style = "Calm"
        elif intuition > calc:
            style = "Creative"
        else:
            style = "Balanced"

        self.user_profile["style_name"] = style
        if not self.user_profile.get("personality_name"):
            self.user_profile["personality_name"] = style

    def _bump(self, profile: dict, key: str, delta: int, low: int = 0, high: int = 100):
        profile[key] = self._clamp(profile.get(key, 50) + delta, low, high)

    def _board_phase(self, board):
        piece_count = len(board.piece_map())

        if board.fullmove_number <= 10 or piece_count >= 24:
            return "opening"
        if piece_count <= 14 or board.fullmove_number >= 40:
            return "endgame"
        return "middlegame"

    def _move_traits(self, board, candidate, best_raw_score):
        move = candidate["move"]

        is_capture = bool(candidate.get("is_capture", board.is_capture(move)))
        gives_check = bool(candidate.get("gives_check", board.gives_check(move)))
        is_promotion = move.promotion is not None
        is_castle = board.is_castling(move)

        piece = board.piece_at(move.from_square)
        moved_piece_type = piece.piece_type if piece is not None else None
        is_non_pawn_piece = moved_piece_type is not None and moved_piece_type != chess.PAWN
        is_quiet = not is_capture and not gives_check and not is_promotion and not is_castle

        raw_score = candidate.get("raw_score", None)
        if raw_score is None:
            raw_score = int(round(float(candidate.get("engine_score", 0)) * 100.0))
        raw_score = float(raw_score)

        score_loss = max(0.0, float(best_raw_score) - raw_score)

        is_sacrifice_like = (
            is_capture
            and is_non_pawn_piece
            and score_loss >= 60
        )

        return {
            "capture": is_capture,
            "check": gives_check,
            "promotion": is_promotion,
            "castle": is_castle,
            "quiet": is_quiet,
            "non_pawn_piece": is_non_pawn_piece,
            "sacrifice_like": is_sacrifice_like,
            "raw_score": raw_score,
            "score_loss": score_loss,
        }

    def record_user_move(self, board_before, move, engine_data):
        if self.user_profile is None:
            return

        if self.mode != "coach":
            return

        self._ensure_profile_defaults()

        self.user_profile["moves_analyzed"] = int(self.user_profile.get("moves_analyzed", 0)) + 1

        move_error = float(engine_data.get("move_error", 0))
        is_capture = bool(engine_data.get("is_capture", False))
        is_check = bool(engine_data.get("is_check", False))
        is_promotion = bool(engine_data.get("is_promotion", False))
        is_castle = bool(engine_data.get("is_castle", False))
        is_sacrifice = bool(engine_data.get("is_sacrifice", False))
        is_endgame = bool(engine_data.get("is_endgame", False))
        is_opening = bool(engine_data.get("is_opening", False))
        piece_moved = engine_data.get("piece_moved", "")
        phase = engine_data.get("phase", "")

        if is_capture:
            self._bump(self.user_profile, "attacking", 1)
            self._bump(self.user_profile, "exchange_preference", 1)
        else:
            self._bump(self.user_profile, "positional", 1)
            self._bump(self.user_profile, "calm", 1)

        if is_check:
            self._bump(self.user_profile, "playful", 1)
            self._bump(self.user_profile, "tactical_preference", 1)
            self._bump(self.user_profile, "king_attack", 1)

        if is_promotion:
            self._bump(self.user_profile, "calculation", 2)
            self._bump(self.user_profile, "endgame_skill", 2)
            self._bump(self.user_profile, "confidence", 1)

        if is_castle:
            self._bump(self.user_profile, "calm", 1)
            self._bump(self.user_profile, "positional", 1)

        if is_sacrifice:
            self._bump(self.user_profile, "risk", 2)
            self._bump(self.user_profile, "sacrifice_tendency", 2)
            self._bump(self.user_profile, "attacking", 1)

        if is_endgame:
            self._bump(self.user_profile, "endgame_skill", 2)
            self._bump(self.user_profile, "studious", 1)

        if is_opening:
            self._bump(self.user_profile, "opening_aggression", 1)
            self._bump(self.user_profile, "opening_flexibility", 1)

        if piece_moved:
            self._bump(self.user_profile, "piece_activity", 1)

        if phase == "opening":
            self._bump(self.user_profile, "opening_aggression", 1)
        elif phase == "middlegame":
            self._bump(self.user_profile, "tactical_preference", 1)
        elif phase == "endgame":
            self._bump(self.user_profile, "endgame_skill", 1)

        if move_error <= 30:
            self._bump(self.user_profile, "calculation", 2)
            self._bump(self.user_profile, "confidence", 1)
            self._bump(self.user_profile, "studious", 1)
        elif move_error >= 150:
            self._bump(self.user_profile, "intuition", 2)
            self._bump(self.user_profile, "emotional", 2)
            self._bump(self.user_profile, "risk", 1)

        self.update_style_name()
        self.save_user_profile()

    def record_opponent_move(self, board_before, move, engine_data):
        if self.opponent_profile is None:
            return

        self._ensure_opponent_defaults()

        move_error = float(engine_data.get("move_error", 0))
        is_capture = bool(engine_data.get("is_capture", False))
        gives_check = bool(engine_data.get("gives_check", False))

        if move_error > 150:
            self._bump(self.opponent_profile, "risk", 2)
        elif move_error < 30:
            self._bump(self.opponent_profile, "risk", -1)

        if is_capture:
            self._bump(self.opponent_profile, "aggression", 1)

        if gives_check:
            self._bump(self.opponent_profile, "tactical", 1)

        if move_error < 50:
            self._bump(self.opponent_profile, "positional", 1)

        self.opponent_profile["moves_seen"] = int(self.opponent_profile.get("moves_seen", 0)) + 1

        recent_errors = self.opponent_profile.setdefault("recent_errors", [])
        recent_errors.append(move_error)
        if len(recent_errors) > 30:
            recent_errors.pop(0)

        self.opponent_profile["average_error"] = (
            sum(recent_errors) / len(recent_errors)
            if recent_errors
            else 0
        )

        self.opponent_profile["confidence"] = min(
            100,
            int(self.opponent_profile["moves_seen"] * 2)
        )

    def estimate_opponent_strength(self):
        if self.opponent_profile is None:
            return self.smoothed_rating

        self._ensure_opponent_defaults()

        avg_error = float(self.opponent_profile.get("average_error", 0))

        if avg_error <= 20:
            target_rating = 2200
        elif avg_error <= 40:
            target_rating = 1900
        elif avg_error <= 70:
            target_rating = 1700
        elif avg_error <= 120:
            target_rating = 1500
        elif avg_error <= 200:
            target_rating = 1300
        else:
            target_rating = 1100

        self.smoothed_rating += (target_rating - self.smoothed_rating) * 0.15

        self.opponent_profile["estimated_rating"] = int(self.smoothed_rating)
        return int(self.smoothed_rating)

    def get_target_play_strength(self):
        opponent_rating = self.estimate_opponent_strength()
        user_rating = int(self.user_profile.get("rating", 1100)) if self.user_profile else 1100

        if self.mode == "coach":
            return 2500

        target_strength = max(
            user_rating + 150,
            opponent_rating + 100
        )

        return min(2500, target_strength)

    def get_analysis_depth(self):
        if self.mode == "coach":
            return 20

        target_strength = self.get_target_play_strength()

        if target_strength >= 2400:
            return 20
        elif target_strength >= 2200:
            return 18
        elif target_strength >= 1800:
            return 16
        elif target_strength >= 1500:
            return 14
        else:
            return 12

    def get_opponent_style(self):
        if self.opponent_profile is None:
            return {
                "aggression": 50,
                "tactical": 50,
                "risk": 50,
                "positional": 50
            }

        self._ensure_opponent_defaults()

        return {
            "aggression": self.opponent_profile.get("aggression", 50),
            "tactical": self.opponent_profile.get("tactical", 50),
            "positional": self.opponent_profile.get("positional", 50),
            "risk": self.opponent_profile.get("risk", 50),
        }

    def filter_losing_moves(self, candidate_moves):
        if not candidate_moves:
            return []

        best_score = max(
            float(candidate.get("raw_score", candidate.get("engine_score", 0) * 100.0))
            for candidate in candidate_moves
        )

        safe_moves = []
        for candidate in candidate_moves:
            raw_score = float(candidate.get("raw_score", candidate.get("engine_score", 0) * 100.0))
            score_loss = best_score - raw_score

            if score_loss <= 120:
                safe_moves.append(candidate)

        return safe_moves if safe_moves else candidate_moves

    def _score_candidate(self, board, candidate, identity, opponent_style, best_raw_score):
        phase = self._board_phase(board)
        traits = self._move_traits(board, candidate, best_raw_score)

        engine_score = float(candidate.get("engine_score", 0))
        raw_score = traits["raw_score"]
        score_loss = traits["score_loss"]

        if self.mode == "coach":
            engine_weight = 12.0
            personality_weight = 0.65
            safety_weight = 0.02
        else:
            engine_weight = 8.0
            personality_weight = 1.0
            safety_weight = 0.03

        score = 0.0

        # Engine is always part of the decision.
        score += engine_score * engine_weight

        # Safety / certainty.
        score -= score_loss * safety_weight
        if score_loss <= 20:
            score += 4.0
        elif score_loss <= 60:
            score += 2.0

        # Identity-led personality matching.
        if traits["capture"]:
            score += identity["attacking"] * 0.20 * personality_weight
            score += identity["exchange_preference"] * 0.10 * personality_weight
            score += identity["sacrifice_tendency"] * 0.08 * personality_weight

        if traits["check"]:
            score += identity["tactical_preference"] * 0.20 * personality_weight
            score += identity["king_attack"] * 0.14 * personality_weight
            score += identity["playful"] * 0.08 * personality_weight

        if traits["promotion"]:
            score += identity["calculation"] * 0.18 * personality_weight
            score += identity["endgame_skill"] * 0.20 * personality_weight
            score += identity["confidence"] * 0.08 * personality_weight

        if traits["castle"]:
            score += identity["calm"] * 0.14 * personality_weight
            score += identity["positional"] * 0.10 * personality_weight

        if traits["quiet"]:
            score += identity["positional"] * 0.16 * personality_weight
            score += identity["calm"] * 0.10 * personality_weight
            score += identity["studious"] * 0.08 * personality_weight

        if traits["non_pawn_piece"]:
            score += identity["piece_activity"] * 0.12 * personality_weight

        if traits["sacrifice_like"]:
            score += identity["risk"] * 0.14 * personality_weight
            score += identity["attacking"] * 0.08 * personality_weight

        # Game phase behavior.
        if phase == "opening":
            if traits["capture"] or traits["check"]:
                score += identity["opening_aggression"] * 0.14 * personality_weight
            else:
                score += identity["opening_flexibility"] * 0.12 * personality_weight

        elif phase == "middlegame":
            score += identity["tactical_preference"] * 0.10 * personality_weight
            score += identity["piece_activity"] * 0.08 * personality_weight

        else:  # endgame
            score += identity["endgame_skill"] * 0.18 * personality_weight
            score += identity["calculation"] * 0.12 * personality_weight

        # Opponent style adjustments.
        if opponent_style.get("aggression", 50) > 70 and traits["capture"]:
            score += 2.5
        if opponent_style.get("tactical", 50) > 70 and traits["check"]:
            score += 2.5
        if opponent_style.get("positional", 50) > 70 and traits["quiet"]:
            score += 1.5
        if opponent_style.get("risk", 50) > 70 and score_loss <= 40:
            score += 1.0

        # Coach mode should stay personality-aware, but engine-dominant.
        # Win mode should stay identity-first, then only strengthen when needed.
        if self.mode == "win":
            if raw_score >= best_raw_score - 40:
                score += 2.0
        else:
            if raw_score >= best_raw_score - 20:
                score += 3.0

        return score

    def select_move(self, board, candidate_moves):
        if self.user_profile is None:
            self.load_user_profile()

        self._ensure_profile_defaults()

        if not candidate_moves:
            return None

        if self.mode == "win":
            candidate_moves = self.filter_losing_moves(candidate_moves)

        if not candidate_moves:
            return None

        identity = self.get_identity_weights()
        opponent_style = self.get_opponent_style()

        best_raw_score = max(
            float(candidate.get("raw_score", candidate.get("engine_score", 0) * 100.0))
            for candidate in candidate_moves
        )

        best_item = None

        for candidate in candidate_moves:
            score = self._score_candidate(
                board=board,
                candidate=candidate,
                identity=identity,
                opponent_style=opponent_style,
                best_raw_score=best_raw_score
            )

            if best_item is None:
                best_item = {
                    "candidate": candidate,
                    "score": score,
                    "raw_score": float(candidate.get("raw_score", candidate.get("engine_score", 0) * 100.0))
                }
                continue

            current_raw = float(candidate.get("raw_score", candidate.get("engine_score", 0) * 100.0))

            if score > best_item["score"]:
                best_item = {
                    "candidate": candidate,
                    "score": score,
                    "raw_score": current_raw
                }
            elif score == best_item["score"] and current_raw > best_item["raw_score"]:
                best_item = {
                    "candidate": candidate,
                    "score": score,
                    "raw_score": current_raw
                }

        return best_item["candidate"] if best_item else None
