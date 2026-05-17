"""
Minimal LiqPay client (no external SDK).

LiqPay Checkout protocol:
  POST https://www.liqpay.ua/api/3/checkout
    data      = base64(json(request))
    signature = base64(sha1(private_key + data + private_key))

Callback verification: identical signature over the posted `data`.
Docs: https://www.liqpay.ua/en/documentation/api/aquiring/checkout/doc
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json as _json
import os
from dataclasses import dataclass

LIQPAY_CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"
LIQPAY_API_VERSION = 3


@dataclass(frozen=True)
class LiqPayConfig:
    public_key: str
    private_key: str
    callback_url: str
    success_url: str
    fail_url: str

    @property
    def is_sandbox(self) -> bool:
        return self.public_key.startswith("sandbox_")

    @property
    def configured(self) -> bool:
        return bool(self.public_key and self.private_key)


def load_config() -> LiqPayConfig:
    return LiqPayConfig(
        public_key=os.getenv("LIQPAY_PUBLIC_KEY", ""),
        private_key=os.getenv("LIQPAY_PRIVATE_KEY", ""),
        callback_url=os.getenv("LIQPAY_CALLBACK_URL", ""),
        success_url=os.getenv("LIQPAY_SUCCESS_URL", ""),
        fail_url=os.getenv("LIQPAY_FAIL_URL", ""),
    )


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def encode_data(payload: dict) -> str:
    return _b64(_json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def sign(data_b64: str, private_key: str) -> str:
    raw = (private_key + data_b64 + private_key).encode("utf-8")
    return _b64(hashlib.sha1(raw).digest())


def verify(data_b64: str, signature_b64: str, private_key: str) -> bool:
    expected = sign(data_b64, private_key)
    return hmac.compare_digest(expected, signature_b64)


def decode_callback(data_b64: str) -> dict:
    return _json.loads(base64.b64decode(data_b64).decode("utf-8"))


def build_checkout(
        cfg: LiqPayConfig,
        *,
        amount: float,
        currency: str,
        description: str,
        order_id: str,
        language: str = "uk",
        action: str = "pay",
) -> tuple[str, str]:
    """Returns (data_b64, signature_b64) ready to be POSTed to LIQPAY_CHECKOUT_URL."""
    payload: dict = {
        "public_key": cfg.public_key,
        "version": LIQPAY_API_VERSION,
        "action": action,
        "amount": amount,
        "currency": currency,
        "description": description,
        "order_id": order_id,
        "language": language,
    }
    if cfg.callback_url:
        payload["server_url"] = cfg.callback_url
    if cfg.success_url:
        payload["result_url"] = cfg.success_url
    if cfg.is_sandbox:
        payload["sandbox"] = 1

    data = encode_data(payload)
    signature = sign(data, cfg.private_key)
    return data, signature
