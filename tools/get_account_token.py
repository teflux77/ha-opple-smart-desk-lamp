#!/usr/bin/env python3
"""
Script minimal et autonome pour récupérer l'access_token + openId/userId de
compte Huawei (étape 1 du flow OAuth), sans dépendre de credential_web.

N'affiche le résultat QUE sur ton écran, en local. Ne l'enregistre dans
aucun fichier. Ne colle jamais ce que ce script affiche dans le chat.

Usage :
    python3 get_account_token.py --start-authorization

Puis suis les instructions affichées (ouvrir l'URL, se logger, coller le
callback hms://).
"""

import argparse
import base64
import hashlib
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE_URL = "https://smartlife-dre.things.dbankcloud.com"
AUTHORIZE_URL = "https://oauth-login1.cloud.huawei.com/oauth2/v3/authorize"
APP_ID = "10406921"
APP_VERSION = "17.0.3.320"
REDIRECT_URI = "hms://redirect_url"
TOKEN_URL = f"{BASE_URL}/smart-life/v2/hms-lite/token"
SCOPES = (
    "openid",
    "https://www.huawei.com/auth/account/base.profile",
    "https://smarthome.com/auth/smarthome/devices",
    "https://smarthome.com/auth/smarthome/skill",
)


def build_authorization_url():
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    query = urllib.parse.urlencode(
        {
            "access_type": "offline",
            "response_type": "code",
            "client_id": APP_ID,
            "ui_locales": "zh-cn",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "scope": " ".join(SCOPES),
            "display": "touch",
            "nonce": nonce,
            "include_granted_scopes": "true",
            "uuid": str(uuid.uuid4()),
            "countryCode": "GB",
            "cVersion": "HwID_6.10.0.300",
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE_URL}?{query}", state


def authorization_code_from_input(value, expected_state=None):
    value = value.strip()
    if not value:
        raise ValueError("authorization input is empty")
    if "://" not in value:
        return value
    callback = urllib.parse.urlparse(value)
    if callback.scheme != "hms" or callback.netloc != "redirect_url":
        raise ValueError("callback must use hms://redirect_url")
    query = urllib.parse.parse_qs(callback.query)
    if expected_state is not None and query.get("state", [None])[0] != expected_state:
        raise ValueError("callback state does not match this authorization attempt")
    code = query.get("code", [""])[0].strip()
    if not code:
        raise ValueError("callback does not contain an authorization code")
    return code


def fetch_token(one_time_code):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": f"HuaweiSmartHome/{APP_VERSION}",
        "x-appId": APP_ID,
        "x-appVersion": APP_VERSION,
        "x-language": "zh-CN",
        "x-ori-app-name": "com.huawei.smarthome",
        "x-phoneOs": "Android",
        "x-requestId": str(uuid.uuid4()),
    }
    body = json.dumps(
        {"appId": APP_ID, "code": urllib.parse.quote(one_time_code, safe="")},
        ensure_ascii=False,
    ).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        print(f"ERROR http={exc.code} body={exc.read()[:500]}")
        raise SystemExit(1)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"ERROR network={exc}")
        raise SystemExit(1)
    return json.loads(raw.decode())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-authorization", action="store_true")
    args = parser.parse_args()

    expected_state = None
    if args.start_authorization:
        url, expected_state = build_authorization_url()
        print("Ouvre cette URL dans une fenêtre privée et autorise sur le domaine Huawei :")
        print(url)
        prompt = "Colle l'URL finale hms://redirect_url?... : "
    else:
        prompt = "Code d'autorisation ou URL hms://redirect_url : "

    # input() et non getpass.getpass() : le champ masqué de getpass casse le
    # copier-coller sur certains terminaux Windows (PowerShell/ConHost). Le
    # code reste visible un instant à l'écran, mais il est à usage unique,
    # consommé immédiatement ci-dessous, et jamais écrit dans un fichier ni
    # journalisé.
    raw_input_value = input(prompt)
    one_time_code = authorization_code_from_input(raw_input_value, expected_state)

    token_response = fetch_token(one_time_code)

    print("\n=== Réponse complète (NE JAMAIS COLLER CECI AILLEURS) ===")
    print(json.dumps(token_response, ensure_ascii=False, indent=2))
    print("===========================================================")
    print("\nRepère access_token et openId/userId ci-dessus pour remplir mqtt_lamp_test.py.")


if __name__ == "__main__":
    main()
