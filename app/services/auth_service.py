import base64
import hashlib
import hmac
import os


PBKDF2_ITERATIONS = 310000


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    encoded_salt = base64.b64encode(salt).decode("utf-8")
    encoded_digest = base64.b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${iterations}${encoded_salt}${encoded_digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_str, encoded_salt, encoded_digest = stored_hash.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    iterations = int(iterations_str)
    salt = base64.b64decode(encoded_salt)

    expected_digest = base64.b64decode(encoded_digest)
    computed_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )

    return hmac.compare_digest(expected_digest, computed_digest)
