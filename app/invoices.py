"""
Invoice persistence in MongoDB (shared Onlik cluster).

Database:   onlik
Collection: invoices     — invoices issued from this site
Collection: webhook_hits — every signature-verified Monobank webhook, including
                           ones for invoices issued elsewhere under the same
                           merchant (`matched` is null for those)

Invoice document shape:
  number        public invoice number, INV-{digit}{3 alphabet chars} (unique, random — intentionally not sortable)
  description   service description shown to the client
  amount_minor  amount in minor units (kopiykas / cents)
  currency      "UAH" | "USD" | "EUR"
  status        pending | created | processing | success | failure | reversed | expired | error
  invoice_id    Monobank invoiceId (set once the payment link is created)
  page_url      Monobank pageUrl
  created_at / updated_at / paid_at   UTC datetimes
  modified_at   Monobank modifiedDate from the latest applied webhook
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.monobank import CCY

log = logging.getLogger("mcp-api.net")

DB_NAME = "onlik"
COLLECTION_NAME = "invoices"
HITS_COLLECTION_NAME = "webhook_hits"

# Number format: INV-{digit}{3 chars from NUMBER_ALPHABET}, e.g. INV-7RZ2.
# The alphabet is digits plus uppercase Latin letters that have no
# identical-looking Cyrillic counterpart (A/B/C/E/H/I/K/M/O/P/T/X/Y excluded),
# so a number can't be mistyped by reading it as Ukrainian/Russian text.
# 0 and 3 are excluded as lookalikes of О and З.
NUMBER_PREFIX = "INV-"
NUMBER_DIGITS = "12456789"
NUMBER_ALPHABET = "12456789DFGJLNQRSUVWZ"
_RESERVE_ATTEMPTS = 20

_client: MongoClient | None = None
_collection: Collection | None = None
_hits: Collection | None = None


def configured() -> bool:
    return bool(os.getenv("MONGODB_URI"))


def _database():
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError("MONGODB_URI is not set")
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client[DB_NAME]


def collection() -> Collection:
    global _collection
    if _collection is None:
        col = _database()[COLLECTION_NAME]
        col.create_index("number", unique=True)
        col.create_index("invoice_id", sparse=True)
        _collection = col
    return _collection


def hits_collection() -> Collection:
    global _hits
    if _hits is None:
        col = _database()[HITS_COLLECTION_NAME]
        col.create_index("invoice_id")
        col.create_index("received_at")
        _hits = col
    return _hits


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_number() -> str:
    return NUMBER_PREFIX + secrets.choice(NUMBER_DIGITS) + "".join(secrets.choice(NUMBER_ALPHABET) for _ in range(3))


def reserve(*, description: str, amount_minor: int, currency: str) -> str:
    """Insert a pending invoice under a fresh unique number and return the number.

    The unique index on `number` is the duplicate check: a collision fails the
    insert and we retry with a new candidate.
    """
    col = collection()
    now = _now()
    for _ in range(_RESERVE_ATTEMPTS):
        number = _new_number()
        try:
            col.insert_one(
                {
                    "number": number,
                    "description": description,
                    "amount_minor": amount_minor,
                    "currency": currency,
                    "status": "pending",
                    "created_at": now,
                    "updated_at": now,
                }
            )
        except DuplicateKeyError:
            continue
        return number
    raise RuntimeError(f"could not allocate a unique invoice number after {_RESERVE_ATTEMPTS} attempts")


def attach_payment_link(number: str, *, invoice_id: str, page_url: str) -> None:
    collection().update_one(
        {"number": number},
        {"$set": {"invoice_id": invoice_id, "page_url": page_url, "status": "created", "updated_at": _now()}},
    )


def mark_error(number: str) -> None:
    collection().update_one(
        {"number": number},
        {"$set": {"status": "error", "updated_at": _now()}},
    )


def _parse_modified_date(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def handle_webhook(payload: dict) -> None:
    """Persist the raw webhook hit, then update the matching invoice if it's ours.

    Hits are recorded for every (signature-verified) webhook, including invoices
    issued elsewhere under the same merchant — those simply stay unmatched.
    """
    hit_id = hits_collection().insert_one(
        {
            "received_at": _now(),
            "invoice_id": payload.get("invoiceId"),
            "reference": payload.get("reference"),
            "status": payload.get("status"),
            "amount": payload.get("amount"),
            "ccy": payload.get("ccy"),
            "modified_date": _parse_modified_date(payload.get("modifiedDate")),
            "matched": None,
            "payload": payload,
        }
    ).inserted_id
    matched = apply_webhook(payload)
    if matched:
        hits_collection().update_one({"_id": hit_id}, {"$set": {"matched": matched}})


def apply_webhook(payload: dict) -> str | None:
    """Update the invoice matching a Monobank status webhook; returns its number.

    Webhooks may arrive repeated and out of order, so a payload older than the
    already-applied `modified_at` is ignored.
    """
    invoice_id = payload.get("invoiceId")
    status = payload.get("status")
    if not invoice_id or not status:
        return None

    col = collection()
    doc = col.find_one({"invoice_id": invoice_id})
    if doc is None:
        log.info("Monobank webhook for invoiceId=%s issued outside this site; hit recorded, no invoice to update", invoice_id)
        return None

    if payload.get("amount") != doc["amount_minor"] or payload.get("ccy") != CCY.get(doc["currency"]):
        log.warning(
            "Monobank webhook amount mismatch for invoice %s: got amount=%s ccy=%s, expected amount=%s ccy=%s",
            doc["number"],
            payload.get("amount"),
            payload.get("ccy"),
            doc["amount_minor"],
            CCY.get(doc["currency"]),
        )

    modified = _parse_modified_date(payload.get("modifiedDate"))
    query: dict = {"_id": doc["_id"]}
    if modified is not None:
        query["$or"] = [{"modified_at": None}, {"modified_at": {"$lte": modified}}]

    update: dict = {"status": status, "modified_at": modified, "updated_at": _now()}
    if status == "success":
        update["paid_at"] = _now()
    result = col.update_one(query, {"$set": update})
    if result.modified_count:
        log.info("Invoice %s -> %s (invoiceId=%s)", doc["number"], status, invoice_id)
    else:
        log.info("Skipped stale webhook for invoice %s (status=%s)", doc["number"], status)
    return doc["number"]
