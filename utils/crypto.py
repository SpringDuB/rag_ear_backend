import base64
import json
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def load_or_create_key_pair(private_path: Path, public_path: Path, passphrase: str | None = None) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    private_key = None
    if private_path.exists():
        private_key = serialization.load_pem_private_key(
            private_path.read_bytes(),
            password=passphrase.encode() if passphrase else None,
        )
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _persist_keys(private_key, private_path, public_path, passphrase)

    public_key = private_key.public_key()
    if not public_path.exists():
        _persist_keys(private_key, private_path, public_path, passphrase)
    return private_key, public_key


def _persist_keys(private_key: rsa.RSAPrivateKey, private_path: Path, public_path: Path, passphrase: str | None = None):
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)

    encryption = BestAvailableEncryption(passphrase.encode()) if passphrase else NoEncryption()
    private_bytes = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    private_path.write_bytes(private_bytes)

    public_bytes = private_key.public_key().public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    public_path.write_bytes(public_bytes)


def decrypt_payload(ciphertext_b64: str, private_key: rsa.RSAPrivateKey) -> dict:
    """
    Decrypts RSA payload. JSEncrypt uses PKCS1 v1.5 padding by default, so we try it first
    and fall back to OAEP if needed.
    """
    decoded = base64.b64decode(ciphertext_b64)
    for scheme in (
        padding.PKCS1v15(),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    ):
        try:
            decrypted_bytes = private_key.decrypt(decoded, scheme)
            return json.loads(decrypted_bytes.decode("utf-8"))
        except ValueError:
            continue
    raise ValueError("Unable to decrypt payload")


def export_public_key_pem(public_key: rsa.RSAPublicKey) -> str:
    return (
        public_key.public_bytes(encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
        .strip()
    )
