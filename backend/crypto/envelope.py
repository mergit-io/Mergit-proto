"""Envelope encryption for stored third-party credentials.

Every OAuth access and refresh token Mergit holds on a user's behalf is sealed here. These
are tokens that can open a pull request, merge it, and post to a Slack workspace, so the
threat being defended is a stolen copy of the database file.

**The design, and why each part is there.**

*AES-256-GCM, not Fernet.* Fernet is the obvious choice and it is the wrong one, for a
single reason: it exposes no associated data. Without AAD, a ciphertext is a free-floating
blob — an attacker with write access to the database can move Alice's sealed GitHub token
into Bob's row, and it will decrypt perfectly, because nothing in the ciphertext says whose
it was. Binding `(user_id, provider, purpose)` as AAD makes that swap fail with
`InvalidTag`, and makes it fail *loudly*.

*`purpose` in the AAD.* Access and refresh tokens live in adjacent columns of the same
row, so `(user_id, provider)` alone does not stop the refresh ciphertext being pasted into
the access column. Refresh tokens are longer-lived and more valuable; that swap is worth
one extra field to prevent.

*Envelope, not a single key.* Each row gets its own data key (DEK), which is itself
encrypted by the key-encryption key (KEK) and stored beside the ciphertext. Two things
fall out of this. Rotating the KEK means re-wrapping short DEKs rather than decrypting and
re-encrypting every token in the table. And deleting one user becomes crypto-shredding —
destroy the row and the plaintext is unrecoverable even from a backup, which is a clean
answer to a GDPR erasure request.

*`kek_id` on every row.* Decrypt with the version that sealed it; encrypt with the current
one. Without a recorded version, rotation is a synchronised rewrite of the whole table and
therefore never actually happens.

**The KEK itself** comes from `MERGIT_KEK_CURRENT` and is read once at startup, after which
`load_keys_and_scrub_env()` removes it from `os.environ`. That is not superstition:
`PUT /api/config/keys` writes secrets *into* `os.environ` at runtime, and `code_exec` used
to hand the entire environment to model-authored Python.
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

#: Identifies the key set held in memory. Persisted per row as `connections.kek_id`.
_CURRENT_ID = "k1"
#: id -> 32 raw bytes. Populated by load_keys_and_scrub_env().
_KEYS: dict[str, bytes] = {}
#: Separate key for audit-log fingerprints, derived from the KEK. A fingerprint must
#: identify a token without being reversible.
_AUDIT_KEY: bytes = b""


class NoKeyConfigured(RuntimeError):
    """Raised when a seal/unseal is attempted with no KEK.

    Deliberately fatal rather than falling back to plaintext. A credential store that
    silently degrades to storing tokens in the clear is worse than one that refuses to
    start, because nothing about it looks wrong.
    """


def _decode_key(raw: str) -> bytes:
    """Accept a base64 key, or hash any other string into one.

    The hash path exists so a developer can put `MERGIT_KEK_CURRENT=dev-only-key` in a
    local .env and have it work. It is not for production, where the value should be
    `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"`.
    """
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(raw.encode()).digest()


def load_keys_and_scrub_env() -> None:
    """Read the KEK(s) into memory, then remove them from the environment.

    Call once, in the lifespan, **before** `worker.start()` — after that point agents run,
    and an agent that can read `os.environ` can read the key that unwraps every stored
    token in the database.
    """
    global _AUDIT_KEY
    from config import settings

    current = os.environ.get("MERGIT_KEK_CURRENT", "") or settings.mergit_kek_current
    if current:
        _KEYS[_CURRENT_ID] = _decode_key(current)

    # "id:base64key,id2:base64key2" — retired keys, kept only so old rows still open.
    previous = os.environ.get("MERGIT_KEK_PREVIOUS", "") or settings.mergit_kek_previous
    for entry in previous.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        key_id, raw = entry.split(":", 1)
        _KEYS[key_id.strip()] = _decode_key(raw.strip())

    for var in ("MERGIT_KEK_CURRENT", "MERGIT_KEK_PREVIOUS"):
        os.environ.pop(var, None)

    if _KEYS:
        _AUDIT_KEY = hashlib.sha256(b"mergit-audit-fp" + _KEYS[_CURRENT_ID]).digest()
        logger.info("credential vault ready (%d key version(s))", len(_KEYS))
    else:
        # Not fatal at boot: a deployment with no connections configured never seals
        # anything. It becomes fatal at the moment someone tries to connect an account.
        logger.warning(
            "MERGIT_KEK_CURRENT is not set — connecting a GitHub or Slack account will "
            "fail. Generate one with: "
            "python -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\""
        )


def configured() -> bool:
    return bool(_KEYS)


def _aad(user_id: str, provider: str, purpose: str) -> bytes:
    """The associated data bound into every ciphertext.

    Authenticated but not encrypted: it must match exactly at decrypt time or GCM raises.
    This is what pins a ciphertext to one user, one provider and one column.
    """
    return f"mergit|v1|{user_id}|{provider}|{purpose}".encode()


def new_dek() -> tuple[str, bytes, bytes]:
    """Mint a data key for a new row. Returns (kek_id, dek, wrapped_dek)."""
    if not _KEYS:
        raise NoKeyConfigured(
            "MERGIT_KEK_CURRENT is not configured, so credentials cannot be stored."
        )
    dek = AESGCM.generate_key(bit_length=256)
    kek = AESGCM(_KEYS[_CURRENT_ID])
    nonce = secrets.token_bytes(12)
    # The wrapping is itself authenticated, with its own AAD naming what it is.
    wrapped = nonce + kek.encrypt(nonce, dek, b"mergit|dek")
    return _CURRENT_ID, dek, wrapped


def unwrap_dek(kek_id: str, wrapped: bytes) -> bytes:
    key = _KEYS.get(kek_id)
    if key is None:
        raise NoKeyConfigured(
            f"no key for kek_id {kek_id!r}. If a key was rotated, the previous value must "
            f"remain in MERGIT_KEK_PREVIOUS until every row has been re-sealed."
        )
    nonce, ct = wrapped[:12], wrapped[12:]
    return AESGCM(key).decrypt(nonce, ct, b"mergit|dek")


def seal(dek: bytes, plaintext: str, *, user_id: str, provider: str,
         purpose: str) -> tuple[bytes, bytes]:
    """Encrypt one secret. Returns (ciphertext, nonce).

    A fresh nonce per call, always. GCM catastrophically loses confidentiality *and*
    authenticity if a nonce is reused with the same key — which is exactly what would
    happen if the access and refresh tokens in one row shared a nonce, since they share
    a DEK.
    """
    if plaintext is None:
        return b"", b""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode(), _aad(user_id, provider, purpose))
    return ct, nonce


def unseal(dek: bytes, ciphertext: bytes, nonce: bytes, *, user_id: str, provider: str,
           purpose: str) -> str:
    """Decrypt one secret, or raise `InvalidTag`.

    `InvalidTag` here is not a corrupt-data error to be swallowed — it means the ciphertext
    did not belong to this (user, provider, purpose). Let it propagate.
    """
    if not ciphertext:
        return ""
    return AESGCM(dek).decrypt(nonce, ciphertext, _aad(user_id, provider, purpose)).decode()


def fingerprint(token: str) -> str:
    """A short, non-reversible identifier for the audit log.

    Enough to answer "was this the same token?" across rows; not enough to reconstruct it.
    Keyed, so it cannot be brute-forced by hashing candidate tokens.
    """
    if not token or not _AUDIT_KEY:
        return ""
    return hmac.new(_AUDIT_KEY, token.encode(), hashlib.sha256).hexdigest()[:16]


__all__ = [
    "InvalidTag", "NoKeyConfigured", "configured", "fingerprint",
    "load_keys_and_scrub_env", "new_dek", "seal", "unseal", "unwrap_dek",
]
