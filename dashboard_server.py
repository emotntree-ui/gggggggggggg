# -*- coding: utf-8 -*-
"""
FreeFire Level Up Bot - Web Dashboard + Auth + Admin + Coupons + Glory Launch
"""

import asyncio
import json
import os
import re
import time
import hashlib
import secrets
from typing import Dict, List, Any, Optional
from aiohttp import web
import urllib3
import requests
import httpx
import jwt
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import ReqCLan_pb2
import encode_id_clan_pb2
import data_pb2
import output_pb2
from google.protobuf.json_format import MessageToDict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
DRIFT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DRIFT")
TEMPLATE_PATH = os.path.join(DRIFT_DIR, "index.html")

OB = "OB55"
KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

GAME_HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9)",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/octet-stream",
    "X-Unity-Version": "2018.4.11f1",
    "X-GA": "v1 1",
    "ReleaseVersion": OB,
    "Expect": "100-continue"
}

REGION_SERVER_MAP = {
    "IND": ("https://client.ind.freefiremobile.com", "client.ind.freefiremobile.com"),
    "ME":  ("https://clientbp.ggblueshark.com", "clientbp.ggblueshark.com"),
    "VN":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "BD":  ("https://clientbp.ggwhitehawk.com", "clientbp.ggwhitehawk.com"),
    "PK":  ("https://clientbp.ggblueshark.com", "clientbp.ggblueshark.com"),
    "SG":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "BR":  ("https://client.us.freefiremobile.com", "client.us.freefiremobile.com"),
    "NA":  ("https://client.us.freefiremobile.com", "client.us.freefiremobile.com"),
    "ID":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "RU":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "TH":  ("https://clientbp.ggpolarbear.com", "clientbp.ggpolarbear.com"),
    "SAC": ("https://client.br.freefiremobile.com", "client.br.freefiremobile.com"),
    "TW":  ("https://client.tw.freefiremobile.com", "client.tw.freefiremobile.com"),
    "CIS": ("https://client.cis.freefiremobile.com", "client.cis.freefiremobile.com"),
}
DEFAULT_SERVER_URL = "https://clientbp.ggblueshark.com"
DEFAULT_HOST = "clientbp.ggblueshark.com"


def encrypt_payload(data):
    return AES.new(KEY, AES.MODE_CBC, IV).encrypt(pad(data, AES.block_size))


def get_server_info(region):
    val = REGION_SERVER_MAP.get(str(region).upper(), DEFAULT_SERVER_URL)
    return val if isinstance(val, tuple) else (val, DEFAULT_HOST)


def get_server_url(region):
    return get_server_info(region)[0]


def fetch_single_clan(clan_id, region, token_cache):
    server_base, host = get_server_info(region)
    url = f"{server_base}/GetClanInfoByClanID"
    try:
        my_data = encode_id_clan_pb2.MyData()
        my_data.field1 = int(clan_id)
        my_data.field2 = 1
        payload = encrypt_payload(my_data.SerializeToString())
    except Exception as e:
        return {"clan_id": clan_id, "error": f"Protobuf failed: {e}"}

    response = None
    for uid, creds in token_cache.items():
        token = creds.get('token')
        if not token:
            continue
        headers = GAME_HEADERS.copy()
        headers["Authorization"] = f"Bearer {token}" if not token.startswith("Bearer ") else token
        headers["Host"] = host
        try:
            res = requests.post(url, headers=headers, data=payload, verify=False, timeout=15.0)
            if res.status_code == 200:
                response = res; break
            elif "expired" in res.text.lower() or res.status_code == 401:
                continue
            else:
                response = res; break
        except Exception:
            continue

    if not response or response.status_code != 200:
        return {"clan_id": clan_id, "error": "All tokens failed or expired"}

    full_response = {}
    resp = None
    try:
        resp = data_pb2.response()
        resp.ParseFromString(response.content)
        full_response = MessageToDict(resp, preserving_proto_field_name=True)
    except Exception:
        pass

    guild_xp = 0
    if resp:
        for field_desc, val in resp.ListFields():
            if field_desc.number == 36 and isinstance(val, int):
                guild_xp = val; break
    if guild_xp == 0 and full_response:
        guild_xp = int(full_response.get("field_36") or full_response.get("xp") or 0)

    return {
        "captain_id": getattr(resp, "captain_id", 0) if resp else full_response.get("captain_id", 0),
        "clan_id": int(clan_id),
        "clan_level": getattr(resp, "rank", 4) if resp else full_response.get("rank", 4),
        "clan_name": getattr(resp, "special_code", None) if resp else (full_response.get("special_code") or f"Guild_{clan_id}"),
        "current_officer": full_response.get("current_officer", 0),
        "current_members": full_response.get("current_members", 1),
        "max_members": full_response.get("max_members", 50),
        "Total guild xp": int(guild_xp),
        "welcome_message": getattr(resp, "welcome_message", "") if resp else full_response.get("welcome_message", ""),
        "region": region, "xp": int(guild_xp),
        "raw_response_bytes": response.content.hex()
    }


async def request_clan_async(jwt_token, clan_id, region):
    server_url = get_server_url(region)
    msg = ReqCLan_pb2.MyMessage()
    msg.field_1 = int(clan_id)
    payload = encrypt_payload(msg.SerializeToString())
    headers = GAME_HEADERS.copy()
    headers["Authorization"] = f"Bearer {jwt_token}" if not jwt_token.startswith("Bearer ") else jwt_token
    url = f"{server_url}/RequestJoinClan"
    async with httpx.AsyncClient(verify=False, timeout=8.0) as client:
        r = await client.post(url, headers=headers, content=payload)
        return r.status_code, r.text


EXP_TABLE: Dict[int, int] = {
    1: 0, 2: 48, 3: 202, 4: 544, 5: 1012, 6: 1844, 7: 2792, 8: 3800,
    9: 4870, 10: 6004, 11: 7192, 12: 8448, 13: 9760, 14: 11140, 15: 12566,
    16: 14060, 17: 15610, 18: 17224, 19: 18902, 20: 20632, 21: 22424, 22: 24278,
    23: 26192, 24: 28166, 25: 30200, 26: 32294, 27: 34448, 28: 37804, 29: 41274,
    30: 44870, 31: 48582, 32: 53394, 33: 58566, 34: 64096, 35: 69994, 36: 76460,
    37: 83506, 38: 91128, 39: 99322, 40: 108092, 41: 120144, 42: 133266, 43: 147472,
    44: 162760, 45: 179126, 46: 196572, 47: 215368, 48: 235516, 49: 257010, 50: 279860,
    51: 304056, 52: 348318, 53: 394982, 54: 444044, 55: 495508, 56: 549364, 57: 633756,
    58: 721744, 59: 813336, 60: 908522, 61: 1041438, 62: 1180352, 63: 1325266,
    64: 1476184, 65: 1634300, 66: 1840946, 67: 2056594, 68: 2281242, 69: 2514880,
    70: 2757530, 71: 3059506, 72: 3372284, 73: 3699456, 74: 4041030, 75: 4397002,
    76: 4829104, 77: 5282204, 78: 5756304, 79: 6251408, 80: 6776502, 81: 7381324,
    82: 8043154, 83: 8752982, 84: 9510808, 85: 10316338, 86: 11277190, 87: 12291748,
    88: 13360304, 89: 14482858, 90: 15659418, 91: 17026708, 92: 18453950, 93: 19941280,
    94: 21488570, 95: 23095858, 96: 24763138, 97: 26490428, 98: 28378704, 99: 30124996,
    100: 32032884
}


# ═══════════════════════════════════════════════════════════════════
#  USERS + SESSIONS
# ═══════════════════════════════════════════════════════════════════
USERS_FILE = "users.json"
_sessions: Dict[str, Dict[str, Any]] = {}
SESSION_TTL = 7 * 86400


def _load_users() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
    return {}


def _save_users(u):
    try:
        tmp = USERS_FILE + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(u, f, indent=2)
        os.replace(tmp, USERS_FILE)
    except Exception:
        pass


def _hash_password(pw, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100_000)
    return f"{salt}${h.hex()}"


def _verify_password(pw, stored):
    try:
        salt = stored.split('$', 1)[0]
        return _hash_password(pw, salt) == stored
    except Exception:
        return False


def _create_session(username, role='user'):
    token = secrets.token_urlsafe(32)
    _sessions[token] = {'username': username, 'role': role, 'created_at': time.time()}
    return token


def _get_session(request):
    token = request.cookies.get('session')
    if not token or token not in _sessions:
        return None
    sess = _sessions[token]
    if time.time() - sess['created_at'] > SESSION_TTL:
        _sessions.pop(token, None); return None
    return sess


def _normalize_username(u):
    return str(u).strip().lower().replace(' ', '_')


def _display_username(u):
    return str(u).replace('_', ' ').upper()


def _seed_admin():
    """Create a first admin without shipping a hard-coded production password."""
    users = _load_users()
    username = _normalize_username(os.environ.get("ADMIN_USERNAME", "admin"))
    configured_password = os.environ.get("ADMIN_PASSWORD")
    if username in users:
        changed = False
        if users[username].get("role") != "admin":
            users[username]["role"] = "admin"
            changed = True
        # An explicitly configured ADMIN_PASSWORD is authoritative. This lets
        # an owner recover access without shipping a default password.
        if configured_password:
            users[username]["password_hash"] = _hash_password(configured_password)
            changed = True
        if changed:
            _save_users(users)
        return
    password = configured_password
    generated = not password
    if generated:
        password = secrets.token_urlsafe(16)
    users[username] = {
        'username': username, 'display_name': _display_username(username),
        'password_hash': _hash_password(password), 'role': 'admin',
        'basic_credits': 0, 'premium_credits': 0,
        'created_at': time.time(), 'seeded': True
    }
    _save_users(users)
    if generated:
        print(f"[BOOTSTRAP] Admin username: {username}")
        print(f"[BOOTSTRAP] One-time password: {password}")
        print("[BOOTSTRAP] Save this password now; set ADMIN_PASSWORD for future deployments.")


# ═══════════════════════════════════════════════════════════════════
#  COUPONS
# ═══════════════════════════════════════════════════════════════════
COUPONS_FILE = "coupons.json"


def _load_coupons():
    if os.path.exists(COUPONS_FILE):
        try:
            with open(COUPONS_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
    return {}


def _save_coupons(c):
    try:
        tmp = COUPONS_FILE + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(c, f, indent=2)
        os.replace(tmp, COUPONS_FILE)
    except Exception:
        pass


def _generate_coupon_code():
    a = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return '-'.join(''.join(secrets.choice(a) for _ in range(4)) for _ in range(3))


# ═══════════════════════════════════════════════════════════════════
#  AUTH HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def handle_auth_signup(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    username = _normalize_username(data.get('username', ''))
    password = str(data.get('password', ''))

    if len(username) < 3:
        return web.json_response({"error": "Username too short"}, status=400)
    if len(username) > 20:
        return web.json_response({"error": "Username too long"}, status=400)
    if not username.replace('_', '').isalnum():
        return web.json_response({"error": "Username must be alphanumeric"}, status=400)
    if len(password) < 6:
        return web.json_response({"error": "Password too short"}, status=400)

    users = _load_users()
    if username in users:
        return web.json_response({"error": "Username already exists"}, status=400)

    users[username] = {
        'username': username, 'display_name': _display_username(username),
        'password_hash': _hash_password(password), 'role': 'user',
        'basic_credits': 0, 'premium_credits': 0, 'created_at': time.time()
    }
    _save_users(users)
    return web.json_response({"success": True, "message": "Account created"})


async def handle_auth_login(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    username = _normalize_username(data.get('username', ''))
    password = str(data.get('password', ''))

    users = _load_users()
    user = users.get(username)
    if not user or not _verify_password(password, user.get('password_hash', '')):
        return web.json_response({"error": "Invalid credentials"}, status=401)

    token = _create_session(username, user.get('role', 'user'))
    response = web.json_response({
        "success": True, "username": username,
        "display_name": user.get('display_name', _display_username(username)),
        "role": user.get('role', 'user')
    })
    response.set_cookie('session', token, httponly=True, secure=request.secure, max_age=SESSION_TTL, path='/', samesite='Lax')
    return response


async def handle_auth_logout(request):
    token = request.cookies.get('session')
    if token and token in _sessions:
        _sessions.pop(token, None)
    response = web.json_response({"success": True})
    response.del_cookie('session', path='/')
    return response


async def handle_auth_me(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    users = _load_users()
    user = users.get(sess['username'], {})
    return web.json_response({
        "username": sess['username'],
        "display_name": user.get('display_name', _display_username(sess['username'])),
        "role": sess.get('role', 'user'),
        "basic_credits": user.get('basic_credits', 0),
        "premium_credits": user.get('premium_credits', 0),
        "max_groups": 10
    })


async def handle_change_password(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    cur = str(data.get('current_password', ''))
    new = str(data.get('new_password', ''))
    if len(new) < 6:
        return web.json_response({"error": "Password too short"}, status=400)

    users = _load_users()
    user = users.get(sess['username'])
    if not user or not _verify_password(cur, user.get('password_hash', '')):
        return web.json_response({"error": "Current password incorrect"}, status=401)

    user['password_hash'] = _hash_password(new)
    _save_users(users)
    return web.json_response({"success": True, "message": "Password changed"})


# ═══════════════════════════════════════════════════════════════════
#  COUPON HANDLERS
# ═══════════════════════════════════════════════════════════════════
async def handle_coupon_create(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    basic = int(data.get('basic_credits', 0) or 0)
    premium = int(data.get('premium_credits', 0) or 0)
    if basic < 0 or premium < 0:
        return web.json_response({"error": "Credits cannot be negative"}, status=400)
    if basic == 0 and premium == 0:
        return web.json_response({"error": "Select at least 1 credit"}, status=400)

    users = _load_users()
    user = users.get(sess['username'])
    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    if basic > user.get('basic_credits', 0):
        return web.json_response({"error": f"Only {user.get('basic_credits', 0)} basic credits"}, status=400)
    if premium > user.get('premium_credits', 0):
        return web.json_response({"error": f"Only {user.get('premium_credits', 0)} premium credits"}, status=400)

    user['basic_credits'] -= basic
    user['premium_credits'] -= premium
    _save_users(users)

    coupons = _load_coupons()
    code = _generate_coupon_code()
    while code in coupons:
        code = _generate_coupon_code()

    coupons[code] = {
        'code': code, 'created_by': sess['username'],
        'basic_credits': basic, 'premium_credits': premium,
        'status': 'active', 'created_at': time.time(),
        'used_by': None, 'used_at': None
    }
    _save_coupons(coupons)
    return web.json_response({
        "success": True,
        "coupon": {"code": code, "basic_credits": basic, "premium_credits": premium}
    })


async def handle_coupon_mine(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response([])
    coupons = _load_coupons()
    mine = [{
        'code': c['code'], 'basic_credits': c.get('basic_credits', 0),
        'premium_credits': c.get('premium_credits', 0), 'status': c.get('status', 'active'),
        'created_at': c.get('created_at'), 'used_by': c.get('used_by'), 'used_at': c.get('used_at')
    } for c in coupons.values() if c.get('created_by') == sess['username']]
    mine.sort(key=lambda x: x.get('created_at') or 0, reverse=True)
    return web.json_response(mine)


async def handle_coupon_redeem(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    code = str(data.get('code', '')).strip().upper()
    if not code:
        return web.json_response({"error": "Code required"}, status=400)

    coupons = _load_coupons()
    coupon = coupons.get(code)
    if not coupon:
        return web.json_response({"error": "Invalid coupon"}, status=404)
    if coupon.get('status') != 'active':
        return web.json_response({"error": f"Already {coupon.get('status')}"}, status=400)
    if coupon.get('created_by') == sess['username']:
        return web.json_response({"error": "Cannot redeem your own coupon"}, status=400)

    users = _load_users()
    user = users.get(sess['username'])
    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    basic = coupon.get('basic_credits', 0)
    premium = coupon.get('premium_credits', 0)
    user['basic_credits'] = user.get('basic_credits', 0) + basic
    user['premium_credits'] = user.get('premium_credits', 0) + premium
    _save_users(users)

    coupon['status'] = 'used'
    coupon['used_by'] = sess['username']
    coupon['used_at'] = time.time()
    _save_coupons(coupons)

    return web.json_response({
        "success": True, "basic_credits": basic, "premium_credits": premium,
        "new_basic": user['basic_credits'], "new_premium": user['premium_credits']
    })


async def handle_coupon_redeemed(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response([])
    coupons = _load_coupons()
    r = [{
        'code': c['code'], 'basic_credits': c.get('basic_credits', 0),
        'premium_credits': c.get('premium_credits', 0),
        'created_by': c.get('created_by'), 'used_at': c.get('used_at')
    } for c in coupons.values() if c.get('used_by') == sess['username']]
    r.sort(key=lambda x: x.get('used_at') or 0, reverse=True)
    return web.json_response(r)


async def handle_coupon_cancel(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    code = str(data.get('code', '')).strip().upper()
    coupons = _load_coupons()
    coupon = coupons.get(code)
    if not coupon:
        return web.json_response({"error": "Not found"}, status=404)
    if coupon.get('created_by') != sess['username']:
        return web.json_response({"error": "Not your coupon"}, status=403)
    if coupon.get('status') != 'active':
        return web.json_response({"error": f"Cannot cancel — {coupon.get('status')}"}, status=400)

    users = _load_users()
    user = users.get(sess['username'])
    if user:
        user['basic_credits'] = user.get('basic_credits', 0) + coupon.get('basic_credits', 0)
        user['premium_credits'] = user.get('premium_credits', 0) + coupon.get('premium_credits', 0)
        _save_users(users)

    coupon['status'] = 'cancelled'
    _save_coupons(coupons)
    return web.json_response({
        "success": True, "message": "Cancelled & refunded",
        "new_basic": user['basic_credits'] if user else 0,
        "new_premium": user['premium_credits'] if user else 0
    })


# ═══════════════════════════════════════════════════════════════════
#  ADMIN HANDLERS
# ═══════════════════════════════════════════════════════════════════
def _require_admin(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    if sess.get('role') != 'admin':
        return web.json_response({"error": "Admin access required"}, status=403)
    return None


async def handle_admin_page(request):
    sess = _get_session(request)
    if not sess or sess.get('role') != 'admin':
        raise web.HTTPFound('/login?msg=Admin+access+required')
    return await serve_drift_file("admin.html")


async def handle_admin_overview(request):
    err = _require_admin(request)
    if err: return err
    users = _load_users()
    coupons = _load_coupons()
    stored_accounts = _read_bot_account_file()
    bot_accounts = len(stored_accounts)
    bot_online = sum(1 for a in bot_state.accounts.values() if a.get("status") in ("ONLINE", "IN_MATCH"))
    return web.json_response({
        "total_users": len(users),
        "total_admins": sum(1 for u in users.values() if u.get('role') == 'admin'),
        "total_basic_credits": sum(u.get('basic_credits', 0) for u in users.values()),
        "total_premium_credits": sum(u.get('premium_credits', 0) for u in users.values()),
        "active_coupons": sum(1 for c in coupons.values() if c.get('status') == 'active'),
        "used_coupons": sum(1 for c in coupons.values() if c.get('status') == 'used'),
        "bot_accounts": bot_accounts,
        "bot_online": bot_online,
        "pending_clans": len(getattr(bot_state, 'pending_clans', {})),
        "uptime": int(time.time() - bot_state.start_time)
    })


async def handle_admin_users(request):
    err = _require_admin(request)
    if err: return err
    users = _load_users()
    r = []
    for u_name, u in users.items():
        acc = bot_state.accounts.get(u_name, {})
        r.append({
            "username": u_name,
            "display_name": u.get('display_name', _display_username(u_name)),
            "role": u.get('role', 'user'),
            "basic_credits": u.get('basic_credits', 0),
            "premium_credits": u.get('premium_credits', 0),
            "created_at": u.get('created_at', 0),
            "seeded": u.get('seeded', False),
            "bot_uid": acc.get('uid'),
            "bot_nickname": acc.get('nickname'),
            "bot_status": acc.get('status', 'OFFLINE'),
            "bot_level": acc.get('level', 0),
        })
    r.sort(key=lambda x: x.get('created_at') or 0, reverse=True)
    return web.json_response(r)


async def handle_admin_user_credits(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    target = _normalize_username(data.get('username', ''))
    basic = int(data.get('basic_credits', 0) or 0)
    premium = int(data.get('premium_credits', 0) or 0)
    mode = str(data.get('mode', 'add')).strip()

    users = _load_users()
    if target not in users:
        return web.json_response({"error": f"User '{target}' not found"}, status=404)

    if mode == 'set':
        users[target]['basic_credits'] = max(0, basic)
        users[target]['premium_credits'] = max(0, premium)
    else:
        users[target]['basic_credits'] = max(0, users[target].get('basic_credits', 0) + basic)
        users[target]['premium_credits'] = max(0, users[target].get('premium_credits', 0) + premium)
    _save_users(users)
    return web.json_response({
        "success": True, "username": target,
        "basic_credits": users[target]['basic_credits'],
        "premium_credits": users[target]['premium_credits']
    })


async def handle_admin_user_role(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    target = _normalize_username(data.get('username', ''))
    role = str(data.get('role', 'user')).strip().lower()
    if role not in ('user', 'admin'):
        return web.json_response({"error": "Role must be user/admin"}, status=400)

    sess = _get_session(request)
    if target == sess['username']:
        return web.json_response({"error": "Cannot change own role"}, status=400)

    users = _load_users()
    if target not in users:
        return web.json_response({"error": "User not found"}, status=404)
    users[target]['role'] = role
    _save_users(users)
    return web.json_response({"success": True, "username": target, "role": role})


async def handle_admin_user_delete(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    target = _normalize_username(data.get('username', ''))
    sess = _get_session(request)
    if target == sess['username']:
        return web.json_response({"error": "Cannot delete yourself"}, status=400)

    users = _load_users()
    if target not in users:
        return web.json_response({"error": "User not found"}, status=404)
    del users[target]
    _save_users(users)
    return web.json_response({"success": True, "deleted": target})


async def handle_admin_user_create(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    username = _normalize_username(data.get('username', ''))
    password = str(data.get('password', ''))
    role = str(data.get('role', 'user')).strip().lower()
    basic = int(data.get('basic_credits', 0) or 0)
    premium = int(data.get('premium_credits', 0) or 0)

    if len(username) < 3:
        return web.json_response({"error": "Username too short"}, status=400)
    if len(password) < 6:
        return web.json_response({"error": "Password too short"}, status=400)
    if role not in ('user', 'admin'):
        return web.json_response({"error": "Invalid role"}, status=400)

    users = _load_users()
    if username in users:
        return web.json_response({"error": "Username exists"}, status=400)

    users[username] = {
        'username': username, 'display_name': _display_username(username),
        'password_hash': _hash_password(password), 'role': role,
        'basic_credits': max(0, basic), 'premium_credits': max(0, premium),
        'created_at': time.time()
    }
    _save_users(users)
    return web.json_response({
        "success": True, "username": username,
        "display_name": users[username]['display_name']
    })


async def handle_admin_all_coupons(request):
    err = _require_admin(request)
    if err: return err
    coupons = _load_coupons()
    r = [{
        "code": c['code'], "created_by": c.get('created_by'),
        "basic_credits": c.get('basic_credits', 0),
        "premium_credits": c.get('premium_credits', 0),
        "status": c.get('status', 'active'),
        "created_at": c.get('created_at'),
        "used_by": c.get('used_by'), "used_at": c.get('used_at')
    } for c in coupons.values()]
    r.sort(key=lambda x: x.get('created_at') or 0, reverse=True)
    return web.json_response(r)


async def handle_admin_coupon_create(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    basic = int(data.get('basic_credits', 0) or 0)
    premium = int(data.get('premium_credits', 0) or 0)
    target = _normalize_username(data.get('for_user', ''))

    if basic < 0 or premium < 0:
        return web.json_response({"error": "Cannot be negative"}, status=400)
    if basic == 0 and premium == 0:
        return web.json_response({"error": "Specify at least 1 credit"}, status=400)

    sess = _get_session(request)
    users = _load_users()
    creator = target if target else sess['username']

    if creator not in users:
        return web.json_response({"error": f"User '{creator}' not found"}, status=404)

    user = users[creator]
    if basic > user.get('basic_credits', 0):
        return web.json_response({"error": f"{creator} has {user.get('basic_credits', 0)} basic only"}, status=400)
    if premium > user.get('premium_credits', 0):
        return web.json_response({"error": f"{creator} has {user.get('premium_credits', 0)} premium only"}, status=400)

    user['basic_credits'] -= basic
    user['premium_credits'] -= premium
    _save_users(users)

    coupons = _load_coupons()
    code = _generate_coupon_code()
    while code in coupons:
        code = _generate_coupon_code()

    coupons[code] = {
        'code': code, 'created_by': creator,
        'basic_credits': basic, 'premium_credits': premium,
        'status': 'active', 'created_at': time.time(),
        'used_by': None, 'used_at': None
    }
    _save_coupons(coupons)
    return web.json_response({
        "success": True,
        "coupon": {"code": code, "basic_credits": basic, "premium_credits": premium}
    })


async def handle_admin_coupon_revoke(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    code = str(data.get('code', '')).strip().upper()
    coupons = _load_coupons()
    coupon = coupons.get(code)
    if not coupon:
        return web.json_response({"error": "Not found"}, status=404)
    if coupon.get('status') != 'active':
        return web.json_response({"error": f"Already {coupon.get('status')}"}, status=400)

    creator = coupon.get('created_by')
    users = _load_users()
    if creator and creator in users:
        users[creator]['basic_credits'] = users[creator].get('basic_credits', 0) + coupon.get('basic_credits', 0)
        users[creator]['premium_credits'] = users[creator].get('premium_credits', 0) + coupon.get('premium_credits', 0)
        _save_users(users)

    coupon['status'] = 'cancelled'
    _save_coupons(coupons)
    return web.json_response({"success": True, "message": "Revoked & refunded"})


async def handle_admin_bot_accounts(request):
    err = _require_admin(request)
    if err: return err
    rows = []
    for item in _read_bot_account_file():
        uid = str(item.get("uid") or ("Token_" + str(item.get("token", ""))[:8] if item.get("token") else ""))
        key = str(item.get("uid") or str(item.get("token", ""))[:10])
        acc = bot_state.accounts.get(str(item.get("uid", "")), {})
        task = bot_state.account_workers.get(key)
        running = bool(task and not task.done())
        rows.append({"uid": uid, "control_id": key, "nickname": acc.get("nickname", ""),
            "region": acc.get("region", ""), "level": acc.get("level", 0),
            "exp": acc.get("current_exp", 0), "gained_exp": acc.get("gained_exp", 0),
            "status": acc.get("status", "ONLINE" if running else "OFFLINE"),
            "matches_played": acc.get("matches_played", 0), "active_matches": acc.get("active_matches", 0),
            "is_paused": acc.get("is_paused", False), "running": running,
            "last_updated": acc.get("last_updated", ""), "kind": "token" if item.get("token") else "uid"})
    rows.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    return web.json_response(rows)


# ═══════════════════════════════════════════════════════════════════
#  GLORY LAUNCH HANDLERS ⭐
# ═══════════════════════════════════════════════════════════════════
async def handle_client_launch(request):
    sess = _get_session(request)
    if not sess:
        return web.json_response({"error": "Not authenticated"}, status=401)
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    clan_id = str(data.get('clan_id', '')).strip()
    region = str(data.get('region', 'IND')).strip().upper()

    if not clan_id or not clan_id.isdigit():
        return web.json_response({"error": "clan_id must be numeric"}, status=400)

    valid = ("IND", "BD", "ME", "BR", "US", "SAC", "NA",
             "SG", "TH", "VN", "ID", "PK", "CIS", "RU", "TW")
    if region not in valid:
        return web.json_response({"error": f"Invalid region: {region}"}, status=400)

    users = _load_users()
    user = users.get(sess['username'])
    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    credit_type = 'premium' if region in ('ME', 'BR', 'US', 'NA', 'SAC') else 'basic'
    available = user.get(f'{credit_type}_credits', 0)
    if available < 1:
        return web.json_response({
            "error": f"Insufficient {credit_type} credits (1 required)",
            "required": 1, "available": available,
            "credit_type": credit_type, "region": region
        }, status=400)

    user[f'{credit_type}_credits'] -= 1
    _save_users(users)

    group_id = "GRP-" + secrets.token_hex(5).upper()
    launched_at = time.time()
    # New launches wait for explicit admin approval; do not run the join worker yet.
    groups = _read_store(GROUPS_FILE, [])
    groups.append({"group_id": group_id, "username": sess["username"], "clan_id": clan_id,
                   "region": region, "credit_type": credit_type, "status": "awaiting_approval",
                   "joined": False, "created_at": launched_at, "refunded": False,
                   "snapshots": []})
    _write_store(GROUPS_FILE, groups[-2000:])
    _record_activity(sess["username"], "group_launched", f"Clan {clan_id} ({region}) awaiting admin approval", group_id, clan_id, "pending")
    bot_state.log(f"🕒 Clan launch request awaiting approval: clan {clan_id} region {region} by {sess['username']}", "info")
    return web.json_response({"success": True, "group_id": group_id, "clan_id": clan_id, "region": region,
        "status": "awaiting_approval", "credit_type": credit_type, "remaining_credits": user[f'{credit_type}_credits'],
        "message": f"Clan {clan_id} launch request sent to admin for approval."})


async def _async_join_group(clan_id, region, launched_by):
    try:
        from clan_join import join_clan_bulk
        res = await join_clan_bulk(clan_id, region)
        joined = int(res.get('success', 0) or 0)
        total = int(res.get('total', 0) or 0)
        groups = _read_store(GROUPS_FILE, [])
        # Bind the result to the exact approved request; don't accidentally update
        # another user's request for the same clan and region.
        candidates = [g for g in groups if str(g.get("clan_id")) == str(clan_id)
                      and str(g.get("region", "")).upper() == str(region).upper()
                      and g.get("status") == "pending"
                      and g.get("username") == launched_by]
        group = max(candidates, key=lambda g: g.get("approved_at", g.get("created_at", 0)), default=None)
        if group:
            group["joined"] = joined > 0
            group["status"] = "active" if joined > 0 else "failed"
            group["joined_count"] = joined
            group["total_count"] = total
            # Store only public result fields; never store tokens or credentials.
            group["join_results"] = [{
                "account_id": str(item.get("account_id", "")),
                "nickname": str(item.get("nickname", "")),
                "success": bool(item.get("success")),
                "status_code": item.get("status_code"),
                "error": str(item.get("error", ""))[:180]
            } for item in (res.get("results") or []) if isinstance(item, dict)]
            group["join_error"] = str(res.get("error", ""))[:300] if not joined else ""
            group["updated_at"] = time.time()
            _write_store(GROUPS_FILE, groups)
            _record_activity(group.get("username"), "group_join_result", f"{joined}/{total} join requests accepted", group.get("group_id"), clan_id, "success" if joined > 0 else "failed")
        if joined > 0:
            entry = bot_state.pending_clans.get(region)
            if entry and str(entry.get("clan_id")) == str(clan_id):
                entry['joined'] = True; entry['joined_at'] = time.time()
            bot_state.log(f"✅ {joined}/{total} bots joined clan {clan_id} ({region})", "success")
        else:
            bot_state.log(f"❌ Clan join failed: {res.get('error', 'no accounts')}", "warning")
    except Exception as e:
        # Make failures visible in My Groups rather than leaving the request stuck.
        try:
            rows = _read_store(GROUPS_FILE, [])
            candidates = [g for g in rows if str(g.get("clan_id")) == str(clan_id)
                          and str(g.get("region", "")).upper() == str(region).upper()
                          and g.get("status") == "pending" and g.get("username") == launched_by]
            group = max(candidates, key=lambda g: g.get("approved_at", g.get("created_at", 0)), default=None)
            if group:
                group["status"] = "failed"
                group["join_error"] = str(e)[:300]
                group["updated_at"] = time.time()
                _write_store(GROUPS_FILE, rows)
                _record_activity(group.get("username"), "group_join_result", str(e)[:300], group.get("group_id"), clan_id, "failed")
        except Exception:
            pass
        bot_state.log(f"❌ Clan join error: {e}", "error")


async def handle_admin_groups(request):
    err = _require_admin(request)
    if err: return err
    rows = _read_store(GROUPS_FILE, [])
    rows.sort(key=lambda g: g.get("created_at", 0), reverse=True)
    return web.json_response(rows[:1000])


async def handle_admin_group_approval(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    gid = str(data.get("group_id", "")).strip()
    decision = str(data.get("decision", "")).lower().strip()
    if not gid or decision not in ("approve", "reject"):
        return web.json_response({"error": "group_id and decision (approve/reject) required"}, status=400)
    rows = _read_store(GROUPS_FILE, [])
    group = next((g for g in rows if str(g.get("group_id")) == gid), None)
    if not group:
        return web.json_response({"error": "Launch request not found"}, status=404)
    if group.get("status") != "awaiting_approval":
        return web.json_response({"error": "Request is no longer awaiting approval", "status": group.get("status")}, status=409)
    if decision == "reject":
        users = _load_users()
        owner = users.get(group.get("username"))
        if owner and not group.get("refunded"):
            credit_key = str(group.get("credit_type", "basic")) + "_credits"
            owner[credit_key] = int(owner.get(credit_key, 0)) + 1
            _save_users(users)
            group["refunded"] = True
            group["refunded_at"] = time.time()
        group["status"] = "rejected"
        group["reviewed_at"] = time.time()
        group["reviewed_by"] = _get_session(request).get("username")
        _write_store(GROUPS_FILE, rows)
        _record_activity(group.get("username"), "group_launch_rejected", gid, gid, group.get("clan_id"), "rejected")
        return web.json_response({"success": True, "group": group, "message": "Launch request rejected; credit refunded when owner account exists."})
    group["status"] = "pending"
    group["approved_at"] = time.time()
    group["reviewed_by"] = _get_session(request).get("username")
    _write_store(GROUPS_FILE, rows)
    region = str(group.get("region", "IND")).upper()
    clan_id = str(group.get("clan_id", ""))
    bot_state.pending_clans[region] = {"group_id": gid, "clan_id": clan_id, "region": region,
        "launched_by": group.get("username"), "launched_at": group.get("created_at", time.time()), "joined": False}
    _record_activity(group.get("username"), "group_launch_approved", gid, gid, clan_id, "approved")
    asyncio.create_task(_async_join_group(clan_id, region, group.get("username", "")))
    return web.json_response({"success": True, "group": group, "message": "Approved. Clan join worker queued."})


async def handle_admin_transactions(request):
    err = _require_admin(request)
    if err: return err
    rows = _read_store(TRANSACTIONS_FILE, [])
    rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return web.json_response(rows[:1000])


async def handle_admin_verify_transaction(request):
    err = _require_admin(request)
    if err: return err
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    txid = str(data.get("transaction_id", data.get("id", ""))).strip()
    decision = str(data.get("decision", "approve")).lower()
    if decision not in ("approve", "reject"):
        return web.json_response({"error": "decision must be approve or reject"}, status=400)
    rows = _read_store(TRANSACTIONS_FILE, [])
    row = next((r for r in rows if r.get("id") == txid), None)
    if not row: return web.json_response({"error": "Transaction not found"}, status=404)
    if row.get("status") != "pending": return web.json_response({"error": "Transaction is not pending"}, status=409)
    if decision == "approve":
        if not row.get("order_id"): return web.json_response({"error": "Order ID is required before approval"}, status=400)
        users = _load_users(); user = users.get(row.get("username"))
        if not user: return web.json_response({"error": "Transaction owner not found"}, status=404)
        user["basic_credits"] = int(user.get("basic_credits", 0)) + int(row.get("basic_credits", 0))
        user["premium_credits"] = int(user.get("premium_credits", 0)) + int(row.get("premium_credits", 0))
        _save_users(users); row["status"] = "completed"; row["verified"] = True
        row["basic_credits_granted"] = int(row.get("basic_credits", 0))
        row["premium_credits_granted"] = int(row.get("premium_credits", 0))
        _record_activity(user["username"], "payment_verified", txid, status="success")
    else:
        row["status"] = "failed"; row["verified"] = False
        _record_activity(row.get("username"), "payment_rejected", txid, status="failed")
    row["updated_at"] = time.time(); _write_store(TRANSACTIONS_FILE, rows)
    return web.json_response({"success": True, "transaction": row})


async def handle_admin_join_clan(request):
    err = _require_admin(request)
    if err: return err
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    clan_id = str(data.get('clan_id', '')).strip()
    region = str(data.get('region', 'IND')).strip().upper()
    uids = data.get('uids')

    if not clan_id:
        return web.json_response({"error": "clan_id required"}, status=400)

    try:
        from clan_join import join_clan_bulk
        return web.json_response(await join_clan_bulk(clan_id, region, uids=uids))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════
#  PERSISTENT DASHBOARD APIs
# ═══════════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSACTIONS_FILE = os.path.join(BASE_DIR, "transactions.json")
MESSAGES_FILE = os.path.join(BASE_DIR, "inbox_messages.json")
NOTIFICATIONS_FILE = os.path.join(BASE_DIR, "notifications.json")
ACTIVITY_FILE = os.path.join(BASE_DIR, "activity_log.json")
GROUPS_FILE = os.path.join(BASE_DIR, "groups.json")
PUSH_FILE = os.path.join(BASE_DIR, "push_subscriptions.json")
ALERTS_FILE = os.path.join(BASE_DIR, "alerts.json")


def _read_store(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError, TypeError):
        return default


def _write_store(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _record_activity(username, action, details="", group_id=None, clan_id=None, status="success"):
    rows = _read_store(ACTIVITY_FILE, [])
    rows.append({"id": secrets.token_hex(8), "username": username, "action": action,
                 "details": str(details)[:500], "group_id": group_id, "clan_id": clan_id,
                 "status": status, "created_at": time.time()})
    _write_store(ACTIVITY_FILE, rows[-1000:])


def _user_rows(path, username, key="username"):
    return [x for x in _read_store(path, []) if x.get(key) == username]


def _load_payment_config():
    config = {}
    try:
        with open(os.path.join(BASE_DIR, "payment_config.json"), "r", encoding="utf-8") as f:
            candidate = json.load(f)
        if isinstance(candidate, dict): config = candidate
    except (OSError, ValueError, TypeError):
        pass
    return config


def _payment_config():
    # Environment variables override UPI receiver details; QR URL is admin-configurable.
    config = _load_payment_config()
    receiver = str(os.environ.get("UPI_RECEIVER_ID", config.get("upi_receiver_id", "")) or "").strip()
    receiver_name = str(os.environ.get("UPI_RECEIVER_NAME", config.get("upi_receiver_name", "Guild Glory")) or "Guild Glory").strip() or "Guild Glory"
    qr_image_url = str(config.get("qr_image_url", "") or "").strip()
    # Only direct HTTP(S) image links ending in JPG/PNG are accepted. QR does not verify payments.
    if qr_image_url and (not re.match(r"^https?://", qr_image_url, re.I) or not re.search(r"\.(?:png|jpe?g)(?:[?#].*)?$", qr_image_url, re.I)):
        qr_image_url = ""
    upi_enabled = bool(receiver and re.fullmatch(r"[A-Za-z0-9._-]{2,256}@[A-Za-z0-9.-]{2,64}", receiver))
    return receiver, receiver_name, upi_enabled, qr_image_url


async def handle_admin_payment_config(request):
    err = _require_admin(request)
    if err: return err
    config = _load_payment_config()
    if request.method == "GET":
        receiver, name, enabled, qr = _payment_config()
        return web.json_response({"upi_receiver_id": receiver, "upi_receiver_name": name,
                                  "qr_image_url": qr, "payment_enabled": bool(enabled or qr),
                                  "upi_from_environment": bool(os.environ.get("UPI_RECEIVER_ID"))})
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    receiver = str(data.get("upi_receiver_id", "") or "").strip()
    name = str(data.get("upi_receiver_name", "Guild Glory") or "Guild Glory").strip()[:100]
    qr = str(data.get("qr_image_url", "") or "").strip()
    if receiver and not re.fullmatch(r"[A-Za-z0-9._-]{2,256}@[A-Za-z0-9.-]{2,64}", receiver):
        return web.json_response({"error": "UPI ID का फॉर्मेट सही नहीं है (जैसे name@bank)"}, status=400)
    if qr and (len(qr) > 2048 or not re.match(r"^https?://", qr, re.I) or not re.search(r"\.(?:png|jpe?g)(?:[?#].*)?$", qr, re.I)):
        return web.json_response({"error": "QR के लिए JPG/PNG का सीधा HTTP(S) लिंक दें"}, status=400)
    config.update({"upi_receiver_id": receiver, "upi_receiver_name": name or "Guild Glory", "qr_image_url": qr})
    try:
        with open(os.path.join(BASE_DIR, "payment_config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError as e:
        return web.json_response({"error": f"Config save failed: {e}"}, status=500)
    _, _, enabled, saved_qr = _payment_config()
    return web.json_response({"success": True, "payment_enabled": bool(enabled or saved_qr), "qr_image_url": saved_qr,
                              "message": "Payment settings saved. QR/UPI payments still need manual verification."})


async def handle_pricing(request):
    _, receiver_name, payment_enabled, qr_image_url = _payment_config()
    return web.json_response({
        "basic_credit_inr": 149.00, "premium_credit_inr": 1799.00,
        "currency": "INR", "payment_provider": "UPI (FamPay app supported)",
        "payment_enabled": bool(payment_enabled or qr_image_url),
        "payment_message": ("Payment QR/UPI is configured. Payment still requires server/admin verification." if (payment_enabled or qr_image_url) else "Payment is not configured. Set a UPI ID or payment QR image in Admin → Account Tools."),
        "receiver_name": receiver_name if payment_enabled else None,
        "qr_image_url": qr_image_url or None,
        "regions": [
            {"id": "ind", "region_name": "India", "tier": "basic", "enabled": True},
            {"id": "bd", "region_name": "Bangladesh", "tier": "basic", "enabled": True},
            {"id": "me", "region_name": "Middle East", "tier": "premium", "enabled": True},
            {"id": "br", "region_name": "Brazil", "tier": "premium", "enabled": True},
        ]})


async def handle_transactions(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    rows = _read_store(TRANSACTIONS_FILE, [])
    rows = [r for r in rows if r.get("username") == sess["username"]]
    rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    for row in rows:
        if isinstance(row.get("created_at"), (int, float)): row["created_at"] = row["created_at"] * 1000
        if isinstance(row.get("updated_at"), (int, float)): row["updated_at"] = row["updated_at"] * 1000
    return web.json_response(rows)


async def handle_buy_credits(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    try:
        basic = int(data.get("basic_credits", 0) or 0)
        premium = int(data.get("premium_credits", 0) or 0)
    except (ValueError, TypeError):
        return web.json_response({"error": "Credit amounts must be whole numbers"}, status=400)
    # Also accept the compact tier/quantity payload for API clients.
    if basic == 0 and premium == 0:
        tier = str(data.get("credit_type", data.get("tier", "basic"))).lower()
        try: qty = int(data.get("quantity", data.get("credits", 0)) or 0)
        except (ValueError, TypeError): qty = 0
        if tier == "basic": basic = qty
        elif tier == "premium": premium = qty
        else: return web.json_response({"error": "credit_type must be basic or premium"}, status=400)
    if basic < 0 or premium < 0 or basic > 10000 or premium > 10000 or (basic == 0 and premium == 0):
        return web.json_response({"error": "Choose 1..10000 credits in at least one category"}, status=400)
    # UTR is optional at order creation; it is collected only after the user pays.
    order_id = str(data.get("order_id", "")).strip()
    if order_id and len(order_id) < 5: return web.json_response({"error": "Payment reference must be at least 5 characters"}, status=400)
    amount = round(basic * 149.00 + premium * 1799.00, 2)
    receiver, receiver_name, upi_enabled, qr_image_url = _payment_config()
    payment_enabled = bool(upi_enabled or qr_image_url)
    txid = "TX-" + secrets.token_hex(6).upper()
    upi_url = None
    if upi_enabled:
        from urllib.parse import urlencode
        upi_url = "upi://pay?" + urlencode({"pa": receiver, "pn": receiver_name, "tr": txid,
                                              "tn": f"Guild Glory {txid}", "am": f"{amount:.2f}", "cu": "INR"})
    row = {"id": txid, "username": sess["username"],
           "basic_credits": basic, "premium_credits": premium,
           "credit_type": "mixed" if basic and premium else ("premium" if premium else "basic"),
           "quantity": basic + premium, "amount": amount, "currency": "INR",
           "status": "pending", "verified": False, "order_id": order_id,
           "created_at": time.time(), "updated_at": time.time(),
           "payment_method": "UPI", "payment_provider": "UPI (FamPay app supported)",
           "payment_enabled": payment_enabled,
           "note": ("UPI payment intent created. Credits remain pending until payment is independently verified." if upi_enabled else ("QR payment selected. Credits remain pending until payment is independently verified." if qr_image_url else "Payment is not configured. No payment was initiated; set a UPI ID or QR image in Admin → Account Tools." ))}
    rows = _read_store(TRANSACTIONS_FILE, [])
    if order_id and any(r.get("order_id") == order_id and r.get("status") != "cancelled" for r in rows):
        return web.json_response({"error": "This order ID is already attached to a transaction"}, status=409)
    rows.append(row); _write_store(TRANSACTIONS_FILE, rows[-5000:])
    _record_activity(sess["username"], "credit_order_created", f"{row['id']} pending; order ID supplied: {bool(order_id)}", status="pending")
    return web.json_response({"success": True, "verified": False, "transaction_id": row["id"],
                              "transaction": row, "upi_url": upi_url,
                              "payment_enabled": payment_enabled, "qr_image_url": qr_image_url or None,
                              "message": ("UPI payment intent ready. Complete payment, then submit the UTR; credits are added only after admin verification." if upi_enabled else ("Payment QR is ready. Scan it, enter the exact order amount, then submit the UTR for admin verification." if qr_image_url else "Order created but payment is disabled until a UPI ID or QR image is configured."))}, status=201)


async def _find_user_transaction(request, data):
    sess = _get_session(request)
    if not sess: return None, None, web.json_response({"error": "Not authenticated"}, status=401)
    txid = str(data.get("transaction_id", data.get("id", ""))).strip()
    rows = _read_store(TRANSACTIONS_FILE, [])
    for row in rows:
        if row.get("id") == txid and row.get("username") == sess["username"]:
            return sess, (rows, row), None
    return sess, None, web.json_response({"error": "Transaction not found"}, status=404)


async def handle_cancel_transaction(request):
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    sess, found, err = await _find_user_transaction(request, data)
    if err: return err
    rows, row = found
    if row.get("status") != "pending": return web.json_response({"error": "Only pending transactions can be cancelled"}, status=409)
    row["status"] = "cancelled"; row["updated_at"] = time.time(); _write_store(TRANSACTIONS_FILE, rows)
    _record_activity(sess["username"], "transaction_cancelled", row["id"])
    return web.json_response({"success": True, "transaction": row})


async def handle_update_transaction_order_id(request):
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    sess, found, err = await _find_user_transaction(request, data)
    if err: return err
    rows, row = found
    order_id = str(data.get("order_id", "")).strip()
    if not order_id or len(order_id) < 5 or len(order_id) > 160: return web.json_response({"error": "Valid payment reference/UTR (at least 5 characters) required"}, status=400)
    if row.get("status") != "pending": return web.json_response({"error": "Only pending transactions can be updated"}, status=409)
    if any(r.get("id") != row.get("id") and str(r.get("order_id", "")).strip().lower() == order_id.lower() and r.get("status") != "cancelled" for r in rows):
        return web.json_response({"error": "This payment reference is already attached to another transaction"}, status=409)
    row["order_id"] = order_id; row["updated_at"] = time.time(); _write_store(TRANSACTIONS_FILE, rows)
    _record_activity(sess["username"], "transaction_order_id_added", row["id"], status="pending")
    return web.json_response({"success": True, "transaction": row})


async def handle_client_groups(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    rows = _read_store(GROUPS_FILE, [])
    rows = [g for g in rows if g.get("username") == sess["username"] or sess.get("role") == "admin"]
    rows.sort(key=lambda g: g.get("created_at", 0), reverse=True)
    time_fields = ("created_at", "updated_at", "approved_at", "reviewed_at", "refunded_at")
    for row in rows:
        for field in time_fields:
            if isinstance(row.get(field), (int, float)):
                row[field] *= 1000
        for snap in row.get("snapshots", []) if isinstance(row.get("snapshots"), list) else []:
            if isinstance(snap, dict) and isinstance(snap.get("captured_at"), (int, float)):
                snap["captured_at"] *= 1000
    return web.json_response(rows)


async def handle_activity_log(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    rows = _read_store(ACTIVITY_FILE, [])
    rows = [r for r in rows if r.get("username") == sess["username"] or sess.get("role") == "admin"]
    rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    mapped = []
    for r in rows[:200]:
        item = dict(r)
        item["timestamp"] = (r.get("created_at", 0) * 1000 if isinstance(r.get("created_at"), (int, float)) else r.get("created_at"))
        item["action"] = {"group_launched": "start", "group_cancel": "stop", "group_dismiss": "delete", "group_refunded": "refund"}.get(r.get("action"), r.get("action"))
        mapped.append(item)
    return web.json_response(mapped)


async def handle_inbox_messages(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    rows = _read_store(MESSAGES_FILE, [])
    visible = [dict(m, is_read=bool(m.get("is_read", m.get("read", False)))) for m in rows if not m.get("dismissed") and m.get("username") in (None, "*", sess["username"])]
    visible.sort(key=lambda m: m.get("created_at", 0), reverse=True)
    for m in visible:
        if isinstance(m.get("created_at"), (int, float)): m["created_at"] *= 1000
    return web.json_response(visible[:200])


async def _mutate_messages(request, action):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    try: data = await request.json()
    except Exception: data = {}
    rows = _read_store(MESSAGES_FILE, []); changed = 0
    mid = str(data.get("id", data.get("message_id", "")))
    for m in rows:
        if m.get("username") not in (None, "*", sess["username"]): continue
        if action == "all" or str(m.get("id")) == mid:
            if action in ("read", "all"):
                m["read"] = True; m["is_read"] = True; changed += 1
            elif action == "dismiss":
                m["dismissed"] = True; changed += 1
    _write_store(MESSAGES_FILE, rows)
    return web.json_response({"success": True, "updated": changed})


async def handle_inbox_mark_read(request): return await _mutate_messages(request, "read")
async def handle_inbox_mark_all_read(request): return await _mutate_messages(request, "all")
async def handle_inbox_dismiss(request): return await _mutate_messages(request, "dismiss")


async def handle_notifications(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    rows = _read_store(NOTIFICATIONS_FILE, [])
    visible = [dict(n) for n in rows if n.get("username") in (None, "*", sess["username"])][:100]
    for n in visible:
        if isinstance(n.get("created_at"), (int, float)): n["created_at"] *= 1000
    return web.json_response(visible)


async def handle_active_alert(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    rows = _read_store(ALERTS_FILE, [])
    for alert in rows:
        if alert.get("active", True) and alert.get("username") in (None, "*", sess["username"]):
            return web.json_response(alert)
    return web.json_response(None)


async def handle_dismiss_alert(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    try: data = await request.json()
    except Exception: data = {}
    aid = str(data.get("id", data.get("alert_id", "")))
    rows = _read_store(ALERTS_FILE, []); changed = False
    for a in rows:
        if a.get("username") in (None, "*", sess["username"]) and (not aid or str(a.get("id")) == aid):
            a["active"] = False; changed = True
    _write_store(ALERTS_FILE, rows)
    return web.json_response({"success": True, "dismissed": changed})


async def handle_push_subscribe(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    sub = data.get("subscription", data)
    if not isinstance(sub, dict) or not isinstance(sub.get("endpoint"), str) or not sub["endpoint"].startswith("https://"):
        return web.json_response({"error": "A valid HTTPS push subscription is required"}, status=400)
    rows = _read_store(PUSH_FILE, [])
    rows = [r for r in rows if not (r.get("username") == sess["username"] and r.get("subscription", {}).get("endpoint") == sub["endpoint"])]
    rows.append({"username": sess["username"], "subscription": sub, "created_at": time.time()})
    _write_store(PUSH_FILE, rows[-1000:])
    return web.json_response({"success": True, "stored": True, "delivery_enabled": bool(os.environ.get("VAPID_PRIVATE_KEY") and os.environ.get("VAPID_PUBLIC_KEY"))})


async def handle_vapid_public_key(request):
    key = os.environ.get("VAPID_PUBLIC_KEY", "")
    return web.json_response({"publicKey": key, "configured": bool(key)})


async def handle_public_contact_info(request):
    return web.json_response({"telegram": os.environ.get("PUBLIC_TELEGRAM_URL", ""),
                              "whatsapp": os.environ.get("PUBLIC_WHATSAPP_URL", "")})


async def handle_group_action(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    gid = str(data.get("group_id", "")).strip(); action = str(data.get("action", "")).lower()
    if not gid: return web.json_response({"error": "group_id required"}, status=400)
    rows = _read_store(GROUPS_FILE, [])
    group = next((g for g in rows if str(g.get("group_id")) == gid and (g.get("username") == sess["username"] or sess.get("role") == "admin")), None)
    if not group: return web.json_response({"error": "Group not found"}, status=404)
    if action == "refund":
        if group.get("refunded"): return web.json_response({"error": "This group has already been refunded"}, status=409)
        if group.get("status") not in ("failed", "cancelled"):
            return web.json_response({"success": False, "message": "Refund is available only for failed or cancelled launches."}, status=409)
        users = _load_users(); u = users.get(group.get("username"))
        if not u: return web.json_response({"error": "Owner account not found"}, status=404)
        tier = group.get("credit_type", "basic") + "_credits"
        u[tier] = int(u.get(tier, 0)) + 1; _save_users(users)
        group["refunded"] = True; group["refunded_at"] = time.time(); _write_store(GROUPS_FILE, rows)
        _record_activity(sess["username"], "group_refunded", gid, gid, group.get("clan_id"))
        return web.json_response({"success": True, "message": "One credit refunded", "basic_credits": u.get("basic_credits", 0), "premium_credits": u.get("premium_credits", 0)})
    if action in ("cancel", "dismiss"):
        group["status"] = "cancelled" if action == "cancel" else group.get("status", "dismissed")
        group["updated_at"] = time.time(); _write_store(GROUPS_FILE, rows)
        _record_activity(sess["username"], "group_" + action, gid, gid, group.get("clan_id"))
        return web.json_response({"success": True, "group": group})
    return web.json_response({"error": "Unsupported action"}, status=400)


async def handle_admin_group_action(request):
    err = _require_admin(request)
    if err: return err
    return await handle_group_action(request)


async def handle_refetch_clan_data(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    gid = str(request.query.get("group_id", ""))
    rows = _read_store(GROUPS_FILE, [])
    group = next((g for g in rows if str(g.get("group_id")) == gid and (g.get("username") == sess["username"] or sess.get("role") == "admin")), None)
    if not group: return web.json_response({"success": False, "message": "Group not found"}, status=404)
    try:
        with open(os.path.join(BASE_DIR, "token_cache.json"), "r", encoding="utf-8") as f:
            token_cache = json.load(f)
        if not isinstance(token_cache, dict) or not token_cache:
            return web.json_response({"success": False, "message": "No cached game tokens are available to query clan details."}, status=503)
        clan_data = await asyncio.to_thread(fetch_single_clan, str(group.get("clan_id", "")), str(group.get("region", "IND")), token_cache)
        if not isinstance(clan_data, dict) or clan_data.get("error"):
            return web.json_response({"success": False, "message": (clan_data or {}).get("error", "Clan data query failed")}, status=502)
        # Never persist the raw protobuf response bytes in the user-facing record.
        clan_data.pop("raw_response_bytes", None)
        group["clan_data"] = clan_data
        snapshots = group.get("snapshots", [])
        if not isinstance(snapshots, list): snapshots = []
        xp = int(clan_data.get("Total guild xp") or clan_data.get("xp") or 0)
        previous = snapshots[-1] if snapshots else {}
        if not previous or int(previous.get("total_guild_xp", -1)) != xp:
            snapshots.append({"captured_at": time.time(), "total_guild_xp": xp,
                              "uptime_hours": round(max(0, time.time() - float(group.get("created_at", time.time()))) / 3600, 2)})
        group["snapshots"] = snapshots[-200:]
        group["updated_at"] = time.time()
        _write_store(GROUPS_FILE, rows)
        _record_activity(sess["username"], "group_clan_data_refreshed", f"Clan {group.get('clan_id')} details refreshed", gid, group.get("clan_id"), "success")
        return web.json_response({"success": True, "message": "Clan details refreshed.", "group": group})
    except Exception as e:
        return web.json_response({"success": False, "message": f"Clan refresh failed: {str(e)[:180]}"}, status=502)


async def handle_glory_progression(request):
    sess = _get_session(request)
    if not sess: return web.json_response({"error": "Not authenticated"}, status=401)
    gid = str(request.query.get("group_id", "")); rows = _read_store(GROUPS_FILE, [])
    group = next((g for g in rows if str(g.get("group_id")) == gid and (g.get("username") == sess["username"] or sess.get("role") == "admin")), None)
    if not group: return web.json_response({"error": "Group not found"}, status=404)
    snapshots = group.get("snapshots", []) if isinstance(group.get("snapshots", []), list) else []
    final_glory = snapshots[-1] if snapshots else None
    first_glory = snapshots[0] if snapshots else None
    final_value = (final_glory or {}).get("total_glory", (final_glory or {}).get("total_guild_xp"))
    first_value = (first_glory or {}).get("total_glory", (first_glory or {}).get("total_guild_xp"))
    try:
        glory_farmed = max(0, int(final_value or 0) - int(first_value or 0)) if len(snapshots) > 1 else 0
    except (TypeError, ValueError):
        glory_farmed = 0
    return web.json_response({"group": group, "clan_data": group.get("clan_data"), "snapshots": snapshots,
                              "final_glory": final_glory, "glory_farmed": glory_farmed})


async def handle_empty_list(request):
    return web.json_response([])


async def handle_null(request):
    return web.json_response(None)


async def handle_vapid_placeholder(request):
    return await handle_vapid_public_key(request)


# ═══════════════════════════════════════════════════════════════════
#  STATIC SERVING
# ═══════════════════════════════════════════════════════════════════
async def serve_drift_file(filename):
    fp = os.path.join(DRIFT_DIR, filename)
    if not os.path.isfile(fp):
        return web.Response(status=404, text=f"DRIFT/{filename} not found")
    return web.FileResponse(fp)


async def handle_ffglory(request): return await serve_drift_file("ffglory.html")
async def handle_login_page(request): return await serve_drift_file("login.html")
async def handle_signup_page(request): return await serve_drift_file("signup.html")
async def handle_client_page(request): return await serve_drift_file("client.html")
async def handle_bot_page(request): return await serve_drift_file("index.html")


async def serve_static(request):
    filename = request.match_info.get('filename', '').lstrip('/')
    if not filename or '..' in filename:
        return web.Response(status=404, text="Not found")
    drift_abs = os.path.abspath(DRIFT_DIR)
    fp = os.path.abspath(os.path.join(drift_abs, filename))
    if not fp.startswith(drift_abs + os.sep) and fp != drift_abs:
        return web.Response(status=404, text="Not found")
    if not os.path.isfile(fp):
        return web.Response(status=404, text="Not found")
    return web.FileResponse(fp)


# ═══════════════════════════════════════════════════════════════════
#  BOT STATE
# ═══════════════════════════════════════════════════════════════════
def calculate_level_progress(level, current_exp):
    level = max(1, level)
    next_level = min(100, level + 1)
    base = EXP_TABLE.get(level, 0)
    target = EXP_TABLE.get(next_level, base + 50000)
    needed = max(1, target - base)
    earned = max(0, current_exp - base)
    remaining = max(0, target - current_exp)
    pct = min(100.0, max(0.0, (earned / needed) * 100.0))
    return {"next_level": next_level, "base_exp": base, "target_exp": target,
            "needed_for_level": needed, "earned_in_level": earned,
            "remaining_exp": remaining, "progress_pct": round(pct, 1)}


class BotState:
    def __init__(self):
        self.accounts = {}
        self.logs = []
        self.max_logs = 200
        self.total_matches = 0
        self.total_matches_started = 0
        self.total_gained_exp = 0
        self.start_time = time.time()
        self.account_workers = {}
        self.account_token_map = {}
        self.auth_to_game_id = {}
        self.game_to_auth_id = {}
        self.paused_accounts = set()
        self.refresh_callbacks = {}
        self.account_credentials = {}
        self.active_writers = {}
        self.pending_clans: Dict[str, Dict[str, Any]] = {}  # ⭐ NEW

    def log(self, message, level="info", uid=None):
        entry = {"time": time.strftime("%H:%M:%S"), "level": level,
                 "message": message, "uid": str(uid) if uid else None}
        self.logs.append(entry)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def register_account(self, uid, nickname, region, level, exp, likes=0, token=None, auth_uid=None):
        uid_str = str(uid)
        prog = calculate_level_progress(level or 1, exp)
        lvl_val = level or 1
        mode = "BR" if lvl_val < 3 else "LONE_WOLF"
        if uid_str not in self.accounts:
            self.accounts[uid_str] = {
                "uid": uid_str, "auth_uid": str(auth_uid) if auth_uid else "",
                "nickname": nickname or f"Player_{uid_str[:6]}",
                "region": region or "BD", "level": lvl_val,
                "next_level": prog["next_level"], "mode": mode,
                "mode_label": "Battle Royale" if lvl_val < 3 else "Lone Wolf",
                "initial_exp": exp, "current_exp": exp, "gained_exp": 0,
                "remaining_exp": prog["remaining_exp"],
                "target_exp": prog["target_exp"],
                "needed_for_level": prog["needed_for_level"],
                "earned_in_level": prog["earned_in_level"],
                "progress_pct": prog["progress_pct"],
                "likes": likes or 0,
                "status": "PAUSED" if self.is_paused(uid_str) else "ONLINE",
                "matches_played": 0, "active_matches": 0, "last_match_time": None,
                "token": token or "", "start_time": time.time(),
                "is_paused": self.is_paused(uid_str), "paused_at": None,
                "total_pause_duration": 0.0,
                "last_updated": time.strftime("%H:%M:%S")
            }
        else:
            acc = self.accounts[uid_str]
            if nickname: acc["nickname"] = nickname
            if region: acc["region"] = region
            if level: acc["level"] = level
            if token: acc["token"] = token
            acc["current_exp"] = exp
            acc["gained_exp"] = max(0, exp - acc["initial_exp"])
            acc["progress_pct"] = prog["progress_pct"]
            acc["last_updated"] = time.strftime("%H:%M:%S")
        self.recalc_totals()

    def get_account_uptime(self, uid_str):
        acc = self.accounts.get(uid_str)
        if not acc: return 0
        start_t = acc.get("start_time", time.time())
        total_pause = acc.get("total_pause_duration", 0.0)
        if acc.get("is_paused") and acc.get("paused_at"):
            return max(0, int(acc["paused_at"] - start_t - total_pause))
        return max(0, int(time.time() - start_t - total_pause))

    def is_paused(self, uid):
        return str(uid) in self.paused_accounts

    def toggle_pause(self, uid):
        uid_str = str(uid)
        is_now_paused = not self.is_paused(uid_str)
        if is_now_paused:
            self.paused_accounts.add(uid_str)
            if uid_str in self.accounts:
                self.accounts[uid_str]["is_paused"] = True
                self.accounts[uid_str]["paused_at"] = time.time()
                self.accounts[uid_str]["status"] = "PAUSED"
        else:
            self.paused_accounts.discard(uid_str)
            if uid_str in self.accounts:
                self.accounts[uid_str]["is_paused"] = False
                self.accounts[uid_str]["paused_at"] = None
                self.accounts[uid_str]["status"] = "ONLINE"
        return is_now_paused

    def toggle_pause_all(self):
        any_active = any(not self.is_paused(k) for k in self.accounts.keys())
        for k in list(self.accounts.keys()):
            current_paused = self.is_paused(k)
            if any_active and not current_paused:
                self.toggle_pause(k)
            elif not any_active and current_paused:
                self.toggle_pause(k)
        return any_active

    def update_exp(self, uid, current_exp, level=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            acc = self.accounts[uid_str]
            old_exp = acc["current_exp"]
            acc["current_exp"] = current_exp
            if level is not None and level > 0:
                acc["level"] = level
            acc["gained_exp"] = max(0, current_exp - acc["initial_exp"])
            prog = calculate_level_progress(acc["level"], current_exp)
            acc["progress_pct"] = prog["progress_pct"]
            acc["last_updated"] = time.strftime("%H:%M:%S")
            diff = current_exp - old_exp
            if diff > 0:
                self.log(f"★ UID {uid_str} gained +{diff:,} EXP", "success", uid_str)
            self.recalc_totals()

    def update_status(self, uid, status, active_matches=None):
        uid_str = str(uid)
        if uid_str in self.accounts:
            self.accounts[uid_str]["status"] = status
            if active_matches is not None:
                self.accounts[uid_str]["active_matches"] = active_matches
            self.accounts[uid_str]["last_updated"] = time.strftime("%H:%M:%S")

    def increment_match(self, uid):
        uid_str = str(uid)
        self.total_matches += 1
        if uid_str in self.accounts:
            self.accounts[uid_str]["matches_played"] += 1
            self.accounts[uid_str]["last_match_time"] = time.strftime("%H:%M:%S")

    def recalc_totals(self):
        self.total_gained_exp = sum(acc.get("gained_exp", 0) for acc in self.accounts.values())


bot_state = BotState()


# ═══════════════════════════════════════════════════════════════════
#  BOT APIs
# ═══════════════════════════════════════════════════════════════════
async def handle_get_stats(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    accounts_data = list(bot_state.accounts.values())
    accounts_data.sort(key=lambda x: x.get("gained_exp", 0), reverse=True)
    uptime_sec = max(1, int(time.time() - bot_state.start_time))
    total_gained = bot_state.total_gained_exp
    exp_per_hour = int((total_gained / uptime_sec) * 3600)
    total_active = sum(acc.get("active_matches", 0) for acc in accounts_data)

    for acc in accounts_data:
        uid_k = str(acc.get("uid", ""))
        acc["uptime_seconds"] = bot_state.get_account_uptime(uid_k)
        acc["is_paused"] = bot_state.is_paused(uid_k)

    return web.json_response({
        "total_accounts": len(bot_state.accounts),
        "total_matches": bot_state.total_matches,
        "total_matches_started": bot_state.total_matches_started,
        "total_active_matches": total_active,
        "total_gained_exp": total_gained,
        "exp_per_hour": exp_per_hour,
        "accounts": accounts_data,
        "logs": bot_state.logs[-80:],
        "uptime": uptime_sec,
        "pending_clans": list(bot_state.pending_clans.keys())
    })


async def handle_api_clan_join(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        data = await request.json()
        clan_id = data.get('clan_id')
        if not clan_id:
            return web.json_response({'error': 'clan_id required'}, status=400)
        try:
            with open("token_cache.json", "r", encoding="utf-8") as f:
                token_cache = json.load(f)
        except Exception as e:
            return web.json_response({'error': f'Cache load failed: {e}'}, status=500)
        success = 0; total = 0
        for uid, creds in token_cache.items():
            jwt_token = creds.get('token')
            region = creds.get('region', 'IND')
            if not jwt_token: continue
            total += 1
            try:
                sc, _ = await request_clan_async(jwt_token, clan_id, region)
                if sc == 200: success += 1
            except Exception:
                pass
        return web.json_response({'message': f'Sent for {success}/{total} accounts'}, status=200)
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


GUILD_CACHE_FILE = "guild_exp_cache.json"


def load_guild_cache():
    if os.path.exists(GUILD_CACHE_FILE):
        try:
            with open(GUILD_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_guild_cache(c):
    try:
        with open(GUILD_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=4)
    except Exception:
        pass


def get_persisted_baseline_xp(clan_id, current_xp):
    cache = load_guild_cache()
    key = str(clan_id)
    if key not in cache or "old_xp" not in cache[key]:
        cache[key] = {"old_xp": current_xp, "live_xp": current_xp, "gained_exp": 0}
        save_guild_cache(cache)
        return current_xp
    return int(cache[key]["old_xp"])


async def handle_api_guild_info(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        clan_id = request.query.get('guild_id') or request.query.get('clan_id')
        region = (request.query.get('region') or 'IND').upper()
        api_key = request.query.get('key')
        if not api_key or api_key != "XEROX_MODS":
            return web.json_response({"error": "Unauthorized"}, status=401)
        if not clan_id:
            return web.json_response({"error": "guild_id required"}, status=400)
        try:
            with open("token_cache.json", "r", encoding="utf-8") as f:
                token_cache = json.load(f)
        except Exception:
            return web.json_response({"error": "Cache load failed"}, status=503)
        if not token_cache:
            return web.json_response({"error": "Empty cache"}, status=503)
        clan_data = fetch_single_clan(clan_id, region, token_cache)
        if "error" in clan_data:
            return web.json_response(clan_data, status=500)
        current_xp = int(clan_data.get("Total guild xp") or clan_data.get("xp") or 0)
        baseline = get_persisted_baseline_xp(clan_id, current_xp)
        gained = current_xp - baseline
        cache = load_guild_cache()
        cache[str(clan_id)] = {"old_xp": baseline, "live_xp": current_xp, "gained_exp": gained}
        save_guild_cache(cache)
        clan_data["old_xp"] = baseline
        clan_data["gained_exp"] = gained
        return web.json_response({
            "status": "success", "requested_region": region, "queried_clan_id": clan_id,
            "api_response": {
                "DEVLOVER": "XEROX_MODS",
                "TIME AND DATE": time.strftime("%I:%M %p, %A, %B %d, %Y"),
                "clan_basic_info": clan_data
            }
        }, status=200)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def _accounts_file_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts.json")


def _read_bot_account_file():
    try:
        with open(_accounts_file_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _save_bot_account_file(rows):
    path = _accounts_file_path()
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f: json.dump(rows, f, indent=2, ensure_ascii=False)
    os.replace(temp, path)


async def handle_admin_accounts_import(request):
    err = _require_admin(request)
    if err: return err
    try: payload = await request.json()
    except Exception: return web.json_response({"error": "JSON सही नहीं है"}, status=400)
    rows = payload.get("accounts") if isinstance(payload, dict) and "accounts" in payload else payload
    if isinstance(rows, dict): rows = [rows]
    if not isinstance(rows, list) or not rows:
        return web.json_response({"error": "JSON array या {\"accounts\":[...]} दें"}, status=400)
    normalized = []
    for i, item in enumerate(rows):
        if not isinstance(item, dict): return web.json_response({"error": f"Entry #{i+1} object होना चाहिए"}, status=400)
        uid, password, token = str(item.get("uid", "") or "").strip(), str(item.get("password", "") or "").strip(), str(item.get("token", "") or "").strip()
        if uid and password: normalized.append({"uid": uid, "password": password})
        elif token: normalized.append({"token": token})
        else: return web.json_response({"error": f"Entry #{i+1}: uid+password या token आवश्यक है"}, status=400)
    existing = _read_bot_account_file()
    by_key = {}
    for item in existing:
        if isinstance(item, dict):
            key = "uid:" + str(item.get("uid", "")) if item.get("uid") else "token:" + str(item.get("token", ""))
            if key not in ("uid:", "token:"): by_key[key] = item
    for item in normalized:
        key = "uid:" + item["uid"] if item.get("uid") else "token:" + item["token"]
        by_key[key] = item
    saved = list(by_key.values())
    try: _save_bot_account_file(saved)
    except OSError as e: return web.json_response({"error": f"accounts.json save failed: {e}"}, status=500)
    callback = bot_state.refresh_callbacks.get("on_account_added")
    started = 0
    if callback:
        for item in normalized:
            try: asyncio.create_task(callback(item)); started += 1
            except Exception: pass
    bot_state.log(f"Imported/updated {len(normalized)} account entries", "success")
    return web.json_response({"success": True, "imported": len(normalized), "total": len(saved), "workers_started": started})


async def handle_admin_bot_control(request):
    err = _require_admin(request)
    if err: return err
    try: data = await request.json()
    except Exception: return web.json_response({"error": "Invalid JSON"}, status=400)
    action = str(data.get("action", "")).lower().strip()
    uid = str(data.get("uid", "")).strip()
    rows = _read_bot_account_file()
    if action not in ("start", "stop", "restart"):
        return web.json_response({"error": "action must be start, stop, or restart"}, status=400)
    selected = rows if data.get("all") is True else [a for a in rows if (str(a.get("uid", "")) == uid if a.get("uid") else str(a.get("token", ""))[:10] == uid or str(a.get("token", "")) == uid)]
    if not selected: return web.json_response({"error": "Account not found in accounts.json"}, status=404)
    start_cb = bot_state.refresh_callbacks.get("on_account_start") or bot_state.refresh_callbacks.get("on_account_added")
    stop_cb = bot_state.refresh_callbacks.get("on_account_stop")
    restart_cb = bot_state.refresh_callbacks.get("on_account_restart")
    changed = 0
    for acc in selected:
        try:
            if action == "stop":
                ident = str(acc.get("uid") or str(acc.get("token", ""))[:10])
                if stop_cb: await stop_cb(ident)
                else:
                    task = bot_state.account_workers.pop(ident, None)
                    if task and not task.done(): task.cancel()
                changed += 1
            elif action == "restart" and restart_cb:
                await restart_cb(acc); changed += 1
            elif action in ("start", "restart") and start_cb:
                await start_cb(acc); changed += 1
            else:
                return web.json_response({"error": "Bot worker callbacks are not ready. Restart the server and try again."}, status=503)
        except Exception as e:
            bot_state.log(f"Bot {action} failed: {e}", "error")
    bot_state.log(f"Bot {action}: {changed} account(s)", "info")
    return web.json_response({"success": True, "action": action, "changed": changed})


async def handle_add_account(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        data = await request.json()
        accounts_file = _accounts_file_path()
        existing = []
        if os.path.exists(accounts_file):
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        if "uid" in data and "password" in data:
            uid = str(data["uid"]).strip()
            pwd = str(data["password"]).strip()
            if not uid or not pwd:
                return web.json_response({"status": "error", "error": "UID+Password required"})
            if uid in bot_state.account_workers:
                try: bot_state.account_workers[uid].cancel()
                except Exception: pass
                bot_state.account_workers.pop(uid, None)
            existing = [a for a in existing if str(a.get("uid", "")) != uid]
            existing.append({"uid": uid, "password": pwd})
            identifier = uid
        elif "token" in data:
            token = str(data["token"]).strip()
            if not token:
                return web.json_response({"status": "error", "error": "Token required"})
            existing = [a for a in existing if a.get("token", "") != token]
            existing.append({"token": token})
            identifier = f"Token_{token[:8]}..."
        else:
            return web.json_response({"status": "error", "error": "Invalid payload"})
        with open(accounts_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        bot_state.log(f"New account: {identifier}", "success")
        if "on_account_added" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_account_added"](data))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_delete_account(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        data = await request.json()
        req_uid = str(data.get("uid", "")).strip()
        accounts_file = _accounts_file_path()
        if data.get("all") is True:
            existing = _read_bot_account_file()
            for item in existing:
                ident = str(item.get("uid") or str(item.get("token", ""))[:10])
                task = bot_state.account_workers.pop(ident, None)
                if task and not task.done(): task.cancel()
            _save_bot_account_file([])
            bot_state.accounts.clear(); bot_state.account_credentials.clear(); bot_state.paused_accounts.clear()
            bot_state.log("All bot accounts deleted", "warning")
            return web.json_response({"status": "ok", "deleted": len(existing)})
        if not req_uid:
            return web.json_response({"status": "error", "error": "UID required"})
        if os.path.exists(accounts_file):
            with open(accounts_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing = [a for a in existing if not (str(a.get("uid", "")) == req_uid or (a.get("token") and (str(a.get("token", "")) == req_uid or str(a.get("token", ""))[:10] == req_uid)))]
            with open(accounts_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        bot_state.accounts.pop(req_uid, None)
        bot_state.account_credentials.pop(req_uid, None)
        task = bot_state.account_workers.pop(req_uid, None)
        if task and not task.done(): task.cancel()
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_refresh_account(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if "on_refresh_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_refresh_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_restart_account(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if "on_restart_account" in bot_state.refresh_callbacks:
            asyncio.create_task(bot_state.refresh_callbacks["on_restart_account"](uid))
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_clear_logs(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    bot_state.logs.clear()
    return web.json_response({"status": "ok"})


async def handle_toggle_pause(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        data = await request.json()
        uid = str(data.get("uid", "")).strip()
        if not uid:
            return web.json_response({"status": "error", "error": "UID required"})
        return web.json_response({"status": "ok", "is_paused": bot_state.toggle_pause(uid)})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_toggle_pause_all(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    try:
        return web.json_response({"status": "ok", "all_paused": bot_state.toggle_pause_all()})
    except Exception as e:
        return web.json_response({"status": "error", "error": str(e)})


async def handle_api_logs(request):
    auth_error = _require_admin(request)
    if auth_error: return auth_error
    logs = []
    for e in bot_state.logs[-80:]:
        if isinstance(e, dict):
            t = e.get("time", ""); msg = e.get("message", ""); lv = e.get("level", "info")
            color = "#34d399" if lv == "success" else ("#f87171" if lv in ("warning", "error") else "#38bdf8")
            logs.append(f'<span style="color:{color}">[{t}] {msg}</span>')
        else:
            logs.append(str(e))
    return web.json_response({"logs": logs}, status=200)


# ═══════════════════════════════════════════════════════════════════
#  START
# ═══════════════════════════════════════════════════════════════════
async def start_web_dashboard(host="0.0.0.0", port=5000):
    _seed_admin()
    app = web.Application()

    # HTML pages
    app.router.add_get("/",       handle_ffglory)
    app.router.add_get("/login",  handle_login_page)
    app.router.add_get("/signup", handle_signup_page)
    app.router.add_get("/client", handle_client_page)
    app.router.add_get("/bot",    handle_bot_page)
    app.router.add_get("/admin",  handle_admin_page)

    # Auth
    app.router.add_post("/api/auth/signup",          handle_auth_signup)
    app.router.add_post("/api/auth/login",           handle_auth_login)
    app.router.add_post("/api/auth/logout",          handle_auth_logout)
    app.router.add_post("/api/auth/change-password", handle_change_password)
    app.router.add_get ("/api/me",                   handle_auth_me)
    app.router.add_get ("/api/logout",               handle_auth_logout)

    # Coupons
    app.router.add_post("/api/coupons/create",   handle_coupon_create)
    app.router.add_get ("/api/coupons/mine",     handle_coupon_mine)
    app.router.add_post("/api/coupons/redeem",   handle_coupon_redeem)
    app.router.add_get ("/api/coupons/redeemed", handle_coupon_redeemed)
    app.router.add_post("/api/coupons/cancel",   handle_coupon_cancel)

    # Admin
    app.router.add_get ("/api/admin/overview",      handle_admin_overview)
    app.router.add_get ("/api/admin/users",         handle_admin_users)
    app.router.add_post("/api/admin/user/credits",  handle_admin_user_credits)
    app.router.add_post("/api/admin/user/role",     handle_admin_user_role)
    app.router.add_post("/api/admin/user/delete",   handle_admin_user_delete)
    app.router.add_post("/api/admin/user/create",   handle_admin_user_create)
    app.router.add_get ("/api/admin/coupons",       handle_admin_all_coupons)
    app.router.add_post("/api/admin/coupon/create", handle_admin_coupon_create)
    app.router.add_post("/api/admin/coupon/revoke", handle_admin_coupon_revoke)
    app.router.add_get ("/api/admin/bot-accounts",  handle_admin_bot_accounts)
    app.router.add_get ("/api/admin/payment-config", handle_admin_payment_config)
    app.router.add_post("/api/admin/payment-config", handle_admin_payment_config)
    app.router.add_post("/api/admin/accounts/import", handle_admin_accounts_import)
    app.router.add_post("/api/admin/bot-control", handle_admin_bot_control)
    app.router.add_get ("/api/admin/transactions", handle_admin_transactions)
    app.router.add_get ("/api/admin/groups", handle_admin_groups)
    app.router.add_post("/api/admin/group-approval", handle_admin_group_approval)
    app.router.add_post("/api/admin/transaction/verify", handle_admin_verify_transaction)
    app.router.add_post("/api/admin/join-clan",     handle_admin_join_clan)

    # ⭐ Glory Launch
    app.router.add_post("/api/client/launch", handle_client_launch)

    # Credits, groups, notifications, inbox and activity APIs
    app.router.add_get("/api/pricing", handle_pricing)
    app.router.add_get("/api/transactions", handle_transactions)
    app.router.add_post("/api/buyCredits", handle_buy_credits)
    app.router.add_post("/api/transaction/cancel", handle_cancel_transaction)
    app.router.add_post("/api/transaction/update-order-id", handle_update_transaction_order_id)
    app.router.add_get("/api/client/groups", handle_client_groups)
    app.router.add_post("/api/client/group-action", handle_group_action)
    app.router.add_post("/api/admin/group-action", handle_admin_group_action)
    app.router.add_get("/api/client/activity-log", handle_activity_log)
    app.router.add_get("/api/client/refetch-clan-data", handle_refetch_clan_data)
    app.router.add_get("/api/client/glory-progression", handle_glory_progression)
    app.router.add_get("/api/inbox/messages", handle_inbox_messages)
    app.router.add_post("/api/inbox/mark-read", handle_inbox_mark_read)
    app.router.add_post("/api/inbox/mark-all-read", handle_inbox_mark_all_read)
    app.router.add_post("/api/inbox/dismiss", handle_inbox_dismiss)
    app.router.add_get("/api/notifications", handle_notifications)
    app.router.add_get("/api/client/active-alert", handle_active_alert)
    app.router.add_post("/api/client/dismiss-alert", handle_dismiss_alert)
    app.router.add_get("/api/vapid-public-key", handle_vapid_public_key)
    app.router.add_post("/api/push/subscribe", handle_push_subscribe)
    app.router.add_get("/api/public/contact-info", handle_public_contact_info)

    # Bot APIs
    app.router.add_post("/api/clanjoin",          handle_api_clan_join)
    app.router.add_get ("/api/guildinfo",         handle_api_guild_info)
    app.router.add_get ("/api/stats",             handle_get_stats)
    app.router.add_get ("/api/logs",              handle_api_logs)
    app.router.add_post("/api/account/add",       handle_add_account)
    app.router.add_post("/api/account/delete",    handle_delete_account)
    app.router.add_post("/api/account/refresh",   handle_refresh_account)
    app.router.add_post("/api/account/restart",   handle_restart_account)
    app.router.add_post("/api/account/pause",     handle_toggle_pause)
    app.router.add_post("/api/account/pause_all", handle_toggle_pause_all)
    app.router.add_post("/api/logs/clear",        handle_clear_logs)

    # Catch-all static (LAST)
    app.router.add_get('/{filename:.*}', serve_static)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner