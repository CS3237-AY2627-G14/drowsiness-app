import hashlib


def hash_token(token: str) -> str:
    encoded_token = token.encode("utf-8")
    token_hash = hashlib.sha256(encoded_token)
    return token_hash.hexdigest()
