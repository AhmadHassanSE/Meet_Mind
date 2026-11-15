"""Encryption for stored connector credentials (Fernet: AES-CBC with an HMAC).

The key comes from ``MEETMIND_SECRET_KEY``. For a local single-machine install a
key file is generated next to the database instead; it is gitignored and must be
kept with the database (without it, connected accounts must reconnect).
"""
import json
import os

from cryptography.fernet import Fernet, InvalidToken

KEY_ENV = 'MEETMIND_SECRET_KEY'


def cipher(key_path):
    key = os.getenv(KEY_ENV)
    if not key:
        path = key_path()
        if not path.exists():
            path.write_text(Fernet.generate_key().decode(), encoding='ascii')
        key = path.read_text(encoding='ascii').strip()
    return Fernet(key.encode())


def seal(value, key_path):
    return cipher(key_path).encrypt(json.dumps(value).encode()).decode()


def unseal(token, key_path):
    try:
        return json.loads(cipher(key_path).decrypt(token.encode()))
    except InvalidToken as error:
        raise ValueError('Stored credentials cannot be decrypted with the current secret key') from error
