print (" [+] Loading basics...")
import os
import json
import urllib
if os.name == 'nt':
    os.system("color")
    os.system("title Social Empires Server")
else:
    import sys
    sys.stdout.write("\x1b]2;Social Empires Server\x07")

print (" [+] Loading game config...")
from get_game_config import get_game_config, patch_game_config

print (" [+] Loading players...")
from get_player_info import get_player_info, get_neighbor_info
from sessions import (load_saved_villages, all_saves_userid, save_info, new_village,
                      fb_friends_str, neighbors, verify_password, apply_daily_bonus,
                      find_userid_by_email, is_valid_email, email_taken)
load_saved_villages()

print (" [+] Loading server...")
from flask import Flask, render_template, send_from_directory, request, redirect, session, abort
from flask.debughelpers import attach_enctype_error_multidict
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from command import command
from engine import timestamp_now
from version import version_name
from constants import Constant
from quests import get_quest_map
from bundle import ASSETS_DIR, STUB_DIR, TEMPLATES_DIR, BASE_DIR

host = os.environ.get('SE_HOST', '127.0.0.1')
port = int(os.environ.get('SE_PORT', '5050'))
public_host = os.environ.get('SE_PUBLIC_HOST', '127.0.0.1' if host == '0.0.0.0' else host)

# Single supported game SWF. Kept as a constant — the multiple-versions
# selector was removed since only 0.9.26b is known-working with Ruffle.
GAME_SWF = "SocialEmpires0926bsec.swf"

app = Flask(__name__, template_folder=TEMPLATES_DIR)

# Hardening (public deploy ready)
# SECRET_KEY: persist across restarts via env var so sessions survive redeploys.
# Fallback to urandom for dev. In production set SE_SECRET_KEY.
app.secret_key = os.environ.get('SE_SECRET_KEY', '').encode() or os.urandom(32)
# Limit request body size (256 KB covers SWF command payloads; anything bigger is abuse).
app.config['MAX_CONTENT_LENGTH'] = 256 * 1024
# Cookie hygiene
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SE_HTTPS', '').lower() in ('1', 'true', 'yes'),
)

# CSRF protection for browser forms. The Flash SWF posts to /dynamic.* routes
# which are exempted below — those are protected by session+USERID match instead.
csrf = CSRFProtect(app)

# Rate limiter. In-memory backend (single worker). For multiple workers, set
# SE_LIMITER_STORAGE_URI="redis://..." and install redis client.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri=os.environ.get('SE_LIMITER_STORAGE_URI', 'memory://'),
    default_limits=[],  # only apply where decorated
)

def _require_matching_userid():
    """Block request unless the form's USERID matches the session. Returns the USERID on success.
    Aborts 401 if not logged in, 403 if USERID doesn't match.
    """
    sess_uid = session.get('USERID')
    if not sess_uid:
        abort(401)
    form_uid = request.form.get('USERID') or request.values.get('USERID')
    if form_uid and form_uid != sess_uid:
        print(f"[SECURITY] USERID mismatch: session={sess_uid} form={form_uid}")
        abort(403)
    return sess_uid

print (" [+] Configuring server routes...")

##########
# ROUTES #
##########

## PAGES AND RESOURCES

@app.route("/", methods=['GET', 'POST'])
@limiter.limit("15 per minute;200 per hour", methods=["POST"])
def login():
    # Log out previous session
    session.pop('USERID', default=None)
    session.pop('GAMEVERSION', default=None)
    # Reload saves. Allows saves modification without server reset
    load_saved_villages()
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        if not email or not password:
            return render_template("login.html", version=version_name,
                                   error="Email e senha são obrigatórios.", email=email), 400
        USERID = find_userid_by_email(email)
        if not USERID or not verify_password(USERID, password):
            print(f"[LOGIN] Failed for email={email!r}")
            return render_template("login.html", version=version_name,
                                   error="Email ou senha incorretos.", email=email), 401
        session['USERID'] = USERID
        session['GAMEVERSION'] = GAME_SWF
        print(f"[LOGIN] {email} -> {USERID}")
        apply_daily_bonus(USERID)
        return redirect("/ruffle.html")
    # GET → login page
    return render_template("login.html", version=version_name)

@app.route("/ruffle.html")
def ruffle():
    if 'USERID' not in session or session['USERID'] not in all_saves_userid():
        return redirect("/")
    USERID = session['USERID']
    GAMEVERSION = session.get('GAMEVERSION', GAME_SWF)
    print(f"[RUFFLE] {USERID}")
    return render_template("ruffle.html",
                           save_info=save_info(USERID),
                           serverTime=timestamp_now(),
                           version=version_name,
                           GAMEVERSION=GAMEVERSION,
                           SERVERIP=public_host)


@app.route("/new.html", methods=['GET', 'POST'])
@limiter.limit("5 per minute;20 per hour", methods=["POST"])
def new():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        if not email or not password:
            return render_template("new.html", version=version_name, email=email,
                                   error="Email e senha são obrigatórios."), 400
        if not is_valid_email(email):
            return render_template("new.html", version=version_name, email=email,
                                   error="Email em formato inválido."), 400
        if email_taken(email):
            return render_template("new.html", version=version_name, email=email,
                                   error="Já existe uma conta com esse email."), 409
        USERID = new_village(email=email, password=password)
        session['USERID'] = USERID
        session['GAMEVERSION'] = GAME_SWF
        apply_daily_bonus(USERID)
        return redirect("/ruffle.html")
    # GET → form
    return render_template("new.html", version=version_name)

@app.route("/crossdomain.xml")
def crossdomain():
    return send_from_directory(STUB_DIR, "crossdomain.xml")

@app.route("/img/<path:path>")
def images(path):
    return send_from_directory(TEMPLATES_DIR + "/img", path)

@app.route("/css/<path:path>")
def css(path):
    return send_from_directory(TEMPLATES_DIR + "/css", path)

## GAME STATIC


@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_projectiles.swf")
def similar_05122012_projectiles():
    return send_from_directory(ASSETS_DIR + "/swf", "20130417_projectiles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_magicParticles.swf")
def similar_05122012_magicParticles():
    return send_from_directory(ASSETS_DIR + "/swf", "20131010_magicParticles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_dynamic.swf")
def similar_05122012_dynamic():
    return send_from_directory(ASSETS_DIR + "/swf", "120608_dynamic.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/<path:path>")
def static_assets_loader(path):
    # Block path traversal: normalize and reject escapes / absolute paths
    safe = os.path.normpath(path)
    if safe.startswith("..") or os.path.isabs(safe) or ".." in safe.split(os.sep):
        return ("", 404)
    path = safe
    if not os.path.exists(ASSETS_DIR + "/"+ path):
        # File does not exists in provided assets
        if not os.path.exists(f"{BASE_DIR}/download_assets/assets/{path}"):
            # Download file from SP's CDN if it doesn't exist

            # Make directory
            directory = os.path.dirname(f"{BASE_DIR}/download_assets/assets/{path}")
            if not os.path.exists(directory):
                os.makedirs(directory)

            # Download File
            URL = f"https://static.socialpointgames.com/static/socialempires/assets/{path}"
            try:
                response = urllib.request.urlretrieve(URL, f"{BASE_DIR}/download_assets/assets/{path}")
            except urllib.error.HTTPError:
                return ("", 404)

            print(f"====== DOWNLOADED ASSET: {URL}")
            return send_from_directory(f"{BASE_DIR}/download_assets/assets", path)
        else:
            # Use downloaded CDN asset
            print(f"====== USING EXTERNAL: download_assets/assets/{path}")
            return send_from_directory(f"{BASE_DIR}/download_assets/assets", path)
    else:
        # Use provided asset
        return send_from_directory(ASSETS_DIR, path)

## GAME DYNAMIC

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/track_game_status.php", methods=['POST'])
@csrf.exempt
def track_game_status_response():
    _require_matching_userid()
    # Flash sends these as query params; use request.values (form + args).
    status = request.values['status']
    installId = request.values['installId']
    user_id = request.values['user_id']

    print(f"track_game_status: status={status}, installId={installId}, user_id={user_id}.")
    return ("", 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_game_config.php", methods=['GET','POST'])
@csrf.exempt
def get_game_config_response():
    _require_matching_userid()
    spdebug = None

    USERID = request.values['USERID']
    user_key = request.values['user_key']
    if 'spdebug' in request.values:
        spdebug = request.values['spdebug']
    language = request.values['language']

    print(f"get_game_config: USERID: {USERID}. --", request.values)
    return get_game_config()

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_player_info.php", methods=['POST'])
@csrf.exempt
def get_player_info_response():
    _require_matching_userid()

    # Flash sends args on the query string; use request.values (form + args).
    USERID = request.values['USERID']
    user_key = request.values['user_key']
    spdebug = request.values.get('spdebug')
    language = request.values['language']
    neighbors = request.values.get('neighbors')
    client_id = request.values['client_id']
    user = request.values.get('user')
    map = int(request.values['map']) if 'map' in request.values else None

    print(f"get_player_info: USERID: {USERID}. user: {user}")

    # Current Player
    if user is None:
        return (get_player_info(USERID), 200)
    # Arthur
    elif user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1 \
    or user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2 \
    or user == Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3:
        return (get_neighbor_info(user, map), 200)
    # Quest
    elif user.startswith("100000"): # Dirty but quick
        return get_quest_map(user)
    # Neighbor
    else:
        return (get_neighbor_info(user, map), 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/sync_error_track.php", methods=['POST'])
@csrf.exempt
def sync_error_track_response():
    _require_matching_userid()
    # Flash sends args on the query string; use request.values.
    USERID = request.values['USERID']
    user_key = request.values['user_key']
    spdebug = request.values.get('spdebug')
    language = request.values['language']
    error = request.values['error']
    current_failed = request.values['current_failed']
    tries = request.values.get('tries')
    survival = request.values['survival']
    previous_failed = request.values['previous_failed']
    description = request.values['description']
    user_id = request.values['user_id']

    print(f"sync_error_track: USERID: {USERID}. [Error: {error}] tries: {tries}.")
    return ("", 200)

@app.route("/null")
def flash_sync_error_response():
    sp_ref_cat = request.values['sp_ref_cat']

    if sp_ref_cat == "flash_sync_error":
        reason = "reload On Sync Error"
    elif sp_ref_cat == "flash_reload_quest":
        reason = "reload On End Quest"
    elif sp_ref_cat == "flash_reload_attack":
        reason = "reload On End Attack"

    print("flash_sync_error", reason, ". --", request.values)
    return redirect("/ruffle.html")

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php", methods=['POST'])
@csrf.exempt
def command_response():
    USERID = _require_matching_userid()

    user_key = request.values['user_key']
    spdebug = request.values.get('spdebug')
    language = request.values['language']
    client_id = request.values['client_id']

    print(f"command: USERID: {USERID}")

    data_str = request.values['data']
    if len(data_str) < 65 or data_str[64] != ';':
        print(f"command: bad payload (len={len(data_str)})")
        return ({"error": "bad payload"}, 400)
    data_hash = data_str[:64]
    data_payload = data_str[65:]
    try:
        data = json.loads(data_payload)
    except json.JSONDecodeError as e:
        print(f"command: bad JSON payload: {e}")
        return ({"error": "bad json"}, 400)

    command(USERID, data)

    return ({"result": "success"}, 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_continent_ranking.php")
@csrf.exempt
def get_continent_ranking_response():
    USERID = _require_matching_userid()
    worldChange = request.values['worldChange']
    spdebug = request.values.get('spdebug')
    town_id = request.values['map']
    user_key = request.values['user_key']

    # Build continent from real neighbors (sorted by level desc, capped at 8)
    neigh_list = neighbors(USERID)
    neigh_list.sort(key=lambda n: n.get("level", 0), reverse=True)
    continent = []
    for i in range(8):
        if i < len(neigh_list):
            n = neigh_list[i]
            continent.append({
                "posicion": i,
                "nivel": n.get("level", 0),
                "user_id": n.get("pid", 0),
            })
        else:
            continent.append({"posicion": i, "nivel": 0})
    response = {"world_id": 0, "continent": continent}
    return(response)


########
# MAIN #
########

print (" [+] Running server...")

if __name__ == '__main__':
    app.run(host=host, port=port, debug=False)
