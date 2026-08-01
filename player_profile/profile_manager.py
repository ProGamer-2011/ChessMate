import json
import os

BASE_DIR = os.path.dirname(__file__)

PROFILE_FILE = os.path.join(
    BASE_DIR,
    "player_profile.json"
)

DEFAULT_PROFILE = {

    "name": "",

    "rating": 1000,

    "chesscom_username": "",

    "personality_name": "",
    "style_name": "",

    "intuition": 50,
    "calculation": 50,

    "attacking": 50,
    "positional": 50,

    "calm": 50,
    "emotional": 50,

    "playful": 50,
    "studious": 50,

    "confidence": 20,

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
    "time_pressure": 50,
    "opening_variety": 50,
    "initiative": 50,
    "pawn_aggression": 50,
    "endgame_patience": 50,

    "last_chesscom_sync": ""
}

def profile_exists():

    if not os.path.exists(PROFILE_FILE):
        return False

    try:

        with open(PROFILE_FILE, "r") as file:
            data = json.load(file)

        return bool(data.get("name"))

    except:
        return False


def load_profile():

    if not profile_exists():
        return DEFAULT_PROFILE.copy()

    with open(PROFILE_FILE, "r") as file:
        return json.load(file)


def save_profile(profile):

    with open(PROFILE_FILE, "w") as file:
        json.dump(
            profile,
            file,
            indent=4
        )
