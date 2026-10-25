"""Safe local card attachments stored beside the board data."""
from __future__ import annotations

import base64
import binascii
import os
import re
import tempfile

from . import cards, model

MAX_BYTES = 5_000_000
MAX_ATTACHMENTS = 20
ATTACHMENTS_DIR = "attachments"


def _clean_name(value):
    name = str(value or "file").replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[\x00-\x1f]", "", name)[:160]
    return name or "file"


def _clean_mime(value):
    mime = str(value or "application/octet-stream").split(";")[0].strip().lower()
    return mime[:100] or "application/octet-stream"


def _extension(name):
    suffix = os.path.splitext(name)[1].lower()
    if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
        return suffix
    return ".bin"


def _safe_path(store, relative):
    root = os.path.realpath(os.path.join(store.home, ATTACHMENTS_DIR))
    path = os.path.realpath(os.path.join(store.home, relative))
    if not path.startswith(root + os.sep):
        raise ValueError("invalid attachment path")
    return path


def save(store, card_ref, name, mime, encoded):
    if not isinstance(encoded, str) or not encoded:
        raise ValueError("attachment data is required")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("attachment data must be valid base64")
    if len(blob) > MAX_BYTES:
        raise ValueError("attachment exceeds 5 MB")
    if not blob:
        raise ValueError("attachment is empty")
    card = model.card_by_ref(store.read(), card_ref)
    if len(card.get("attachments") or []) >= MAX_ATTACHMENTS:
        raise ValueError("a card can have at most 20 attachments")
    clean_name = _clean_name(name)
    clean_mime = _clean_mime(mime)
    attachment_id = model.new_id("a")
    relative = os.path.join(ATTACHMENTS_DIR, card["id"], attachment_id + _extension(clean_name))
    target = os.path.join(store.home, relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=os.path.dirname(target), delete=False)
    try:
        with handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except OSError:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    metadata = {
        "id": attachment_id,
        "name": clean_name,
        "mime": clean_mime,
        "size": len(blob),
        "stored_as": relative,
        "ts": model.now_iso(),
        "actor": "human",
    }
    try:
        store.mutate(lambda data: cards.add_attachment(data, "human", card["id"], metadata))
    except Exception:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    return metadata


def read(store, card_ref, attachment_ref):
    data = store.read()
    card = model.card_by_ref(data, card_ref)
    matches = [item for item in card.get("attachments") or []
               if item.get("id") == attachment_ref]
    if not matches:
        raise LookupError("attachment not found")
    attachment = matches[0]
    path = _safe_path(store, attachment.get("stored_as") or "")
    with open(path, "rb") as handle:
        blob = handle.read()
    return attachment, blob
