import json
import os
import re
import copy
import uuid
import random
import threading
import hashlib
import hmac
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
# from flask_session import SqlAlchemySessionInterface, current_app

from version import version_code
from engine import timestamp_now
from version import migrate_loaded_save
from constants import Constant

from bundle import VILLAGES_DIR, SAVES_DIR

__villages = {}  # ALL static neighbors
'''__villages = {
    "USERID_1": {
        "playerInfo": {...},
        "maps": [{...},{...}]
        "privateState": {...}
    },
    "USERID_2": {...}
}'''

__saves = {}  # ALL saved villages
'''__saves = {
    "USERID_1": {
        "playerInfo": {...},
        "maps": [{...},{...}]
        "privateState": {...}
    },
    "USERID_2": {...}
}'''

__initial_village = json.load(open(os.path.join(VILLAGES_DIR, "initial.json")))

# Load saved villages

def load_saved_villages():
    global __villages
    global __saves
    # Empty in memory
    __villages = {}
    __saves = {}
    # Saves dir check
    if not os.path.exists(SAVES_DIR):
        try:
            print(f"Creating '{SAVES_DIR}' folder...")
            os.mkdir(SAVES_DIR)
        except:
            print(f"Could not create '{SAVES_DIR}' folder.")
            exit(1)
    if not os.path.isdir(SAVES_DIR):
        print(f"'{SAVES_DIR}' is not a folder... Move the file somewhere else.")
        exit(1)
    # Static neighbors in /villages
    for file in os.listdir(VILLAGES_DIR):
        if file == "initial.json" or not file.endswith(".json"):
            continue
        print(f" * Loading static neighbour {file}... ", end='')
        village = json.load(open(os.path.join(VILLAGES_DIR, file)))
        if not is_valid_village(village):
            print("Invalid neighbour")
            continue
        USERID = village["playerInfo"]["pid"]
        if str(USERID) in __villages:
            print(f"Ignored: duplicated PID '{USERID}'.")
        else:
            __villages[str(USERID)] = village
            print("Ok.")
    # Saves in /saves
    for file in os.listdir(SAVES_DIR):
        if not file.endswith(".save.json"):
            continue
        print(f" * Loading save at {file}... ", end='')
        try:
            save = json.load(open(os.path.join(SAVES_DIR, file)))
        except json.decoder.JSONDecodeError as e:
            print("Corrupted JSON.")
            continue
        if not is_valid_village(save):
            print("Invalid Save.")
            continue
        USERID = save["playerInfo"]["pid"]
        try:
            map_name = save["playerInfo"]["map_names"][ save["playerInfo"]["default_map"] ]
        except:
            map_name = '?'
        print(f"({map_name}) Ok.")
        __saves[str(USERID)] = save
        modified = migrate_loaded_save(save) # check save version for migration
        if modified:
            save_session(USERID)
    

# Password helpers
# New hashes use Werkzeug's PBKDF2 (format: "pbkdf2:sha256:<iter>$<salt>$<hex>" or scrypt).
# Legacy hashes are plain SHA-256 hex (64 chars, no "$" or ":"). They are verified
# with the old algorithm and upgraded to the new format on successful login.

_HASH_METHOD = "pbkdf2:sha256:260000"

def _hash_password(password: str) -> str:
    return generate_password_hash(password, method=_HASH_METHOD)

def _legacy_hash(USERID: str, password: str) -> str:
    return hashlib.sha256((USERID + ":" + password).encode("utf-8")).hexdigest()

def _is_legacy_hash(stored: str) -> bool:
    # Werkzeug hashes contain "$" (and start with method prefix like "pbkdf2:" or "scrypt:").
    # Legacy SHA-256 hex is 64 chars with no separators.
    return "$" not in stored

def village_has_password(USERID: str) -> bool:
    save = session(USERID)
    if save is None:
        return False
    return bool(save["playerInfo"].get("password_hash"))

def verify_password(USERID: str, password: str) -> bool:
    save = session(USERID)
    if save is None:
        return False
    stored = save["playerInfo"].get("password_hash")
    if not stored:
        return True  # no password set on this village
    password = password or ""
    if _is_legacy_hash(stored):
        # Legacy SHA-256 — constant-time check, then upgrade to new format on success.
        candidate = _legacy_hash(USERID, password)
        if hmac.compare_digest(candidate, stored):
            save["playerInfo"]["password_hash"] = _hash_password(password)
            save_session(USERID)
            print(f" [+] Upgraded password hash to {_HASH_METHOD} for {USERID}")
            return True
        return False
    # Modern Werkzeug hash
    return check_password_hash(stored, password)

def set_password(USERID: str, password: str):
    save = session(USERID)
    if save is None:
        return
    save["playerInfo"]["password_hash"] = _hash_password(password) if password else None
    save_session(USERID)

# Email helpers

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def is_valid_email(email: str) -> bool:
    if not email or len(email) > 200:
        return False
    return bool(_EMAIL_RE.match(email))

def find_userid_by_email(email: str) -> str:
    """Return USERID for a given email (case-insensitive), or None."""
    if not email:
        return None
    target = email.strip().lower()
    for uid, vill in __saves.items():
        stored = (vill["playerInfo"].get("email") or "").lower()
        if stored and stored == target:
            return uid
    return None

def email_taken(email: str) -> bool:
    return find_userid_by_email(email) is not None


# New village

def new_village(email: str, password: str) -> str:
    """Create a new village. Both email and password are required."""
    assert email and is_valid_email(email), "valid email required"
    assert password, "password required"
    assert not email_taken(email), "email already registered"
    # Generate USERID
    USERID: str = str(uuid.uuid4())
    assert USERID not in all_userid()
    # Copy init
    village = copy.deepcopy(__initial_village)
    # Custom values
    village["version"] = version_code
    village["playerInfo"]["pid"] = USERID
    village["playerInfo"]["email"] = email.strip().lower()
    # Empire name defaults to the local-part of the email (before @).
    display_name = email.split("@", 1)[0][:40] or "Emperor"
    village["playerInfo"]["name"] = display_name
    village["playerInfo"]["map_names"] = [display_name]
    village["playerInfo"]["password_hash"] = _hash_password(password)
    village["maps"][0]["timestamp"] = timestamp_now()
    village["privateState"]["dartsRandomSeed"] = abs(int((2**16 - 1) * random.random()))
    # Memory saves
    __saves[USERID] = village
    # Generate save file
    save_session(USERID)
    print(f"New village created: {email} -> {USERID}")
    return USERID

# Access functions

def all_saves_userid() -> list:
    "Returns a list of the USERID of every saved village."
    return list(__saves.keys())

def all_userid() -> list:
    "Returns a list of the USERID of every village."
    return list(__villages.keys()) + list(__saves.keys())

def save_info(USERID: str) -> dict:
    save = __saves[USERID]
    default_map = save["playerInfo"]["default_map"]
    empire_name = str(save["playerInfo"]["map_names"][default_map])
    xp = save["maps"][default_map]["xp"]
    level = save["maps"][default_map]["level"]
    has_password = bool(save["playerInfo"].get("password_hash"))
    return{"userid": USERID, "name": empire_name, "xp": xp, "level": level, "has_password": has_password}

def all_saves_info() -> list:
    saves_info = []
    for userid in __saves:
        saves_info.append(save_info(userid))
    return list(saves_info)

def session(USERID: str) -> dict:
    assert(isinstance(USERID, str))
    return __saves[USERID] if USERID in __saves else None

def neighbor_session(USERID: str) -> dict:
    assert(isinstance(USERID, str))
    if USERID in __saves:
        return __saves[USERID]
    if USERID in __villages:
        return __villages[USERID]

def fb_friends_str(USERID: str) -> list:
    DELETE_ME = [{"uid": "1111", "pic_square":"http://127.0.0.1:5050/img/profile/Paladin_Justiciero.jpg"},
        {"uid": "aa_002", "pic_square":"/1025.png"}]
    friends = []
    # static villages
    for key in __villages:
        vill = __villages[key]
        # Avoid Arthur being loaded as friend.
        if vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
            continue
        frie = {}
        frie["uid"] = vill["playerInfo"]["pid"]
        frie["pic_square"] = vill["playerInfo"]["pic"]
        if not frie["pic_square"]: frie["pic_square"] = "/img/profile/1025.png"
        friends += [frie]
    # other players
    for key in __saves:
        vill = __saves[key]
        if vill["playerInfo"]["pid"] == USERID:
            continue
        frie = {}
        frie["uid"] = vill["playerInfo"]["pid"]
        frie["pic_square"] = vill["playerInfo"]["pic"]
        if not frie["pic_square"]: frie["pic_square"] = "/img/profile/1025.png"
        friends += [frie]
    return friends

def neighbors(USERID: str) -> list:
    neighbors = []
    # static villages
    for key in __villages:
        vill = __villages[key]
        # Avoid Arthur being loaded as multiple neigtbors.
        if vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
        or vill["playerInfo"]["pid"] == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
            continue
        neigh = vill["playerInfo"]
        neigh["coins"] = vill["maps"][0]["coins"]
        neigh["xp"] = vill["maps"][0]["xp"]
        neigh["level"] = vill["maps"][0]["level"]
        neigh["stone"] = vill["maps"][0]["stone"]
        neigh["wood"] = vill["maps"][0]["wood"]
        neigh["food"] = vill["maps"][0]["food"]
        neigh["stone"] = vill["maps"][0]["stone"]
        neighbors += [neigh]
    # other players
    for key in __saves:
        vill = __saves[key]
        if vill["playerInfo"]["pid"] == USERID:
            continue
        neigh = vill["playerInfo"]
        neigh["coins"] = vill["maps"][0]["coins"]
        neigh["xp"] = vill["maps"][0]["xp"]
        neigh["level"] = vill["maps"][0]["level"]
        neigh["stone"] = vill["maps"][0]["stone"]
        neigh["wood"] = vill["maps"][0]["wood"]
        neigh["food"] = vill["maps"][0]["food"]
        neigh["stone"] = vill["maps"][0]["stone"]
        neighbors += [neigh]
    return neighbors

# Check for valid village
# The reason why this was implemented is to warn the user if a save game from Social Wars was used by accident

def is_valid_village(save: dict):
    if "playerInfo" not in save or "maps" not in save or "privateState" not in save:
        # These are obvious
        return False
    for map in save["maps"]:
        if "oil" in map or "steel" in map:
            return False
        if "stone" not in map or "food" not in map:
            return False
        if "items" not in map:
            return False
        if type(map["items"]) != list:
            return False

    return True

# Persistency

def backup_session(USERID: str):
    # TODO 
    return

_save_lock = threading.Lock()

# Daily bonus: rotates through DAILY_BONUS_CONFIG each time >=20h passed since last claim.
# Heroes ("hero" type) are given as gifts via save["privateState"]["gifts"] if possible;
# otherwise fall back to giving the quantity as cash (safe default).
_DAILY_MIN_HOURS = 20

def apply_daily_bonus(USERID: str):
    """Apply daily bonus if >=20h passed since last claim. Returns the reward dict or None."""
    from get_game_config import get_game_config
    save = session(USERID)
    if save is None:
        return None
    ps = save["privateState"]
    last_bonus = ps.get("lastDailyBonus", 0)
    now = timestamp_now()
    if last_bonus and (now - last_bonus) < _DAILY_MIN_HOURS * 3600:
        return None

    rewards = get_game_config()["globals"].get("DAILY_BONUS_CONFIG", [])
    if not rewards:
        return None

    day = ps.get("dailyBonusDay", 0)
    reward = rewards[day % len(rewards)]
    qty = int(reward.get("qty", 0))
    rtype = reward.get("type")

    if rtype == "g":
        save["maps"][0]["coins"] += qty
    elif rtype == "c":
        save["playerInfo"]["cash"] += qty
    elif rtype == "hero":
        # Give a generic hero gift: cash equivalent (fallback — picking a specific hero id
        # requires matching the HEROES global and is beyond scope).
        save["playerInfo"]["cash"] += qty
    else:
        print(f"  apply_daily_bonus: unknown reward type {rtype!r}, skipping")
        return None

    ps["dailyBonusDay"] = (day + 1) % len(rewards)
    ps["lastDailyBonus"] = now
    save_session(USERID)
    print(f" [+] Daily bonus applied for {USERID}: +{qty} {rtype} (day {day})")
    return reward

def save_session(USERID: str):
    file = f"{USERID}.save.json"
    print(f" * Saving village at {file}... ", end='')
    village = session(USERID)
    with _save_lock:
        with open(os.path.join(SAVES_DIR, file), 'w') as f:
            json.dump(village, f, indent=4)
    print("Done.")