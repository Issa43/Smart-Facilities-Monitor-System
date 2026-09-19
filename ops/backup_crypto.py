"""Streaming authenticated encryption for SFLMS backup artifacts."""

import argparse
import os
import struct
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"SFLMSBK1"
CHUNK_SIZE = 1024 * 1024


def key_for(passphrase: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000
    ).derive(passphrase.encode("utf-8"))


def encrypt(source: Path, destination: Path, passphrase: str) -> None:
    salt, nonce = os.urandom(16), os.urandom(12)
    encryptor = Cipher(algorithms.AES(key_for(passphrase, salt)), modes.GCM(nonce)).encryptor()
    with source.open("rb") as incoming, destination.open("wb") as outgoing:
        outgoing.write(MAGIC + salt + nonce)
        while chunk := incoming.read(CHUNK_SIZE):
            outgoing.write(encryptor.update(chunk))
        encryptor.finalize()
        outgoing.write(encryptor.tag)


def decrypt(source: Path, destination: Path | None, passphrase: str) -> None:
    size = source.stat().st_size
    with source.open("rb") as incoming:
        if incoming.read(len(MAGIC)) != MAGIC:
            raise ValueError("Invalid SFLMS backup header")
        salt, nonce = incoming.read(16), incoming.read(12)
        incoming.seek(-16, os.SEEK_END)
        tag = incoming.read(16)
        incoming.seek(len(MAGIC) + 28)
        remaining = size - len(MAGIC) - 28 - 16
        decryptor = Cipher(
            algorithms.AES(key_for(passphrase, salt)), modes.GCM(nonce, tag)
        ).decryptor()
        outgoing = destination.open("wb") if destination else None
        try:
            while remaining:
                chunk = incoming.read(min(CHUNK_SIZE, remaining))
                remaining -= len(chunk)
                clear = decryptor.update(chunk)
                if outgoing:
                    outgoing.write(clear)
            decryptor.finalize()
        finally:
            if outgoing:
                outgoing.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("encrypt", "decrypt", "verify"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", nargs="?", type=Path)
    args = parser.parse_args()
    passphrase = os.environ.get("BACKUP_ENCRYPTION_PASSPHRASE")
    if not passphrase or len(passphrase) < 20:
        raise SystemExit("BACKUP_ENCRYPTION_PASSPHRASE must contain at least 20 characters")
    if args.mode == "encrypt":
        if not args.destination:
            raise SystemExit("encrypt requires a destination")
        encrypt(args.source, args.destination, passphrase)
    else:
        if args.mode == "decrypt" and not args.destination:
            raise SystemExit("decrypt requires a destination")
        decrypt(args.source, args.destination if args.mode == "decrypt" else None, passphrase)


if __name__ == "__main__":
    main()
