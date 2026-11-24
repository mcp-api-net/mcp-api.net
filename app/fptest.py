"""
Browser-fingerprint test page (/test) and its collector.

The page is a vendored build of CreepJS (https://github.com/abrahamjuliot/creepjs,
MIT; commit in app/creepjs/VERSION) plus a small collector script
(app/creepjs/collect.js) that POSTs the result to /test/collect.

Storage: MongoDB on the same cluster as the site (MONGODB_URI), but in its own
database — FP_DB_NAME, default `fingerprints` — collection `fp_tests`.

Document shape:
  received_at   UTC datetime
  tag           free-form label set on the page (?tag=… or the input), to group runs by behavior
  ip            client IP as seen by the app (behind Caddy, from X-Forwarded-For)
  user_agent    request User-Agent header
  headers       request headers as [name, value] pairs, in the order the app received them
                (Caddy may reorder/normalize them, so don't rely on order for HTTP fingerprinting)
  fp_id / fuzzy CreepJS FP ID and fuzzy hash as displayed on the page
  computed_ms   time from page script start until CreepJS finished
  page_url, referrer
  fingerprint   window.Fingerprint (full CreepJS output)
  creep         window.Creep (the stable subset CreepJS hashes into FP ID)

Results are readable at /test/results?token=… (summary list) and
/test/results/{id}?token=… (full document) when FP_TEST_TOKEN is set; without
it those endpoints 404.
"""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING, MongoClient
from pymongo.collection import Collection

COLLECTION_NAME = "fp_tests"
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_TAG_LEN = 120

_client: MongoClient | None = None
_collection: Collection | None = None


def configured() -> bool:
    return bool(os.getenv("MONGODB_URI"))


def db_name() -> str:
    return os.getenv("FP_DB_NAME") or "fingerprints"


def collection() -> Collection:
    global _client, _collection
    if _collection is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        col = _client[db_name()][COLLECTION_NAME]
        col.create_index([("received_at", DESCENDING)])
        col.create_index("tag")
        col.create_index("fp_id")
        _collection = col
    return _collection


def token_ok(token: str | None) -> bool:
    expected = os.getenv("FP_TEST_TOKEN")
    return bool(expected) and bool(token) and hmac.compare_digest(token, expected)


def _str_or_none(value, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] or None


def save(payload: dict, *, ip: str | None, headers: list[tuple[str, str]]) -> str:
    headers_map = {k.lower(): v for k, v in headers}
    doc = {
        "received_at": datetime.now(timezone.utc),
        "tag": _str_or_none(payload.get("tag"), MAX_TAG_LEN),
        "ip": ip,
        "user_agent": headers_map.get("user-agent"),
        "headers": [[k, v] for k, v in headers if k.lower() != "cookie"],
        "fp_id": _str_or_none(payload.get("fp_id"), 128),
        "fuzzy": _str_or_none(payload.get("fuzzy"), 128),
        "computed_ms": payload.get("computed_ms") if isinstance(payload.get("computed_ms"), (int, float)) else None,
        "page_url": _str_or_none(payload.get("page_url"), 2048),
        "referrer": _str_or_none(payload.get("referrer"), 2048),
        "fingerprint": payload.get("fingerprint"),
        "creep": payload.get("creep"),
    }
    return str(collection().insert_one(doc).inserted_id)


def _jsonable(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("received_at"), datetime):
        doc["received_at"] = doc["received_at"].isoformat()
    return doc


def recent(*, limit: int = 50, tag: str | None = None) -> list[dict]:
    query = {"tag": tag} if tag else {}
    projection = {"fingerprint": 0, "creep": 0, "headers": 0}
    cursor = collection().find(query, projection).sort("received_at", DESCENDING).limit(max(1, min(limit, 500)))
    return [_jsonable(d) for d in cursor]


def get(doc_id: str) -> dict | None:
    try:
        oid = ObjectId(doc_id)
    except (InvalidId, TypeError):
        return None
    doc = collection().find_one({"_id": oid})
    return _jsonable(doc) if doc else None
