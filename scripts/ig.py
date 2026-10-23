"""Small helpers for the Instagram API with Instagram Login (graph.instagram.com)."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")
BASE = f"https://graph.instagram.com/{API_VERSION}"


class IGError(RuntimeError):
    pass


def _request(method, url, params):
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}", method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        # Never echo the access token back into logs.
        raise IGError(f"HTTP {e.code} from {url.split('?')[0]}: {body}") from None


def get(path, token, **params):
    return _request("GET", f"{BASE}/{path}", {**params, "access_token": token})


def post(path, token, **params):
    return _request("POST", f"{BASE}/{path}", {**params, "access_token": token})


def me(token):
    return get("me", token, fields="user_id,username")


def wait_ready(container_id, token, timeout=180):
    """Wait until a media container finishes processing."""
    deadline = time.time() + timeout
    while True:
        status = get(container_id, token, fields="status_code,status").get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise IGError(f"container {container_id} status {status}")
        if time.time() > deadline:
            raise IGError(f"container {container_id} still {status} after {timeout}s")
        time.sleep(5)
