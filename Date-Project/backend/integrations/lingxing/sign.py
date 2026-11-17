from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


def sign(params: Mapping[str, Any], app_secret: str) -> str:
    pairs = []
    for key in sorted(params):
        pairs.append(f"{key}={_string_value(params[key])}")
    md5_text = hashlib.md5("&".join(pairs).encode("utf-8")).hexdigest().upper()
    return _aes_ecb_pkcs7_base64(md5_text, app_secret)


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return str(value).strip()


def _aes_ecb_pkcs7_base64(text: str, key: str) -> str:
    key_bytes = key.encode("utf-8")
    padder = PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(text.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("ascii")
