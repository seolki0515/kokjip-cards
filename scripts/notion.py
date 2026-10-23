"""Minimal Notion REST client (stdlib only)."""
import json
import os
import urllib.error
import urllib.request

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


class NotionError(RuntimeError):
    pass


def _call(method, path, body=None):
    token = os.environ["NOTION_TOKEN"].strip()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}/{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Notion-Version": VERSION,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise NotionError(f"Notion {method} {path}: HTTP {e.code} {e.read().decode(errors='replace')}") from None


def query(db_id, filter_):
    out, cursor = [], None
    while True:
        body = {"filter": filter_, "page_size": 50}
        if cursor:
            body["start_cursor"] = cursor
        res = _call("POST", f"databases/{db_id}/query", body)
        out += res["results"]
        if not res.get("has_more"):
            return out
        cursor = res["next_cursor"]


def children(block_id):
    out, cursor = [], None
    while True:
        q = f"blocks/{block_id}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
        res = _call("GET", q)
        out += res["results"]
        if not res.get("has_more"):
            return out
        cursor = res["next_cursor"]


def update_page(page_id, properties):
    return _call("PATCH", f"pages/{page_id}", {"properties": properties})


def plain(prop):
    """Plain text of a title / rich_text / select / date / url property."""
    if not prop:
        return ""
    t = prop["type"]
    if t in ("title", "rich_text"):
        return "".join(x["plain_text"] for x in prop[t])
    if t in ("select", "status"):
        return (prop[t] or {}).get("name", "")
    if t == "date":
        return (prop["date"] or {}).get("start", "")
    if t == "url":
        return prop["url"] or ""
    if t == "number":
        return "" if prop["number"] is None else str(prop["number"])
    return ""


def download(url, dest):
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
