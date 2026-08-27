import uuid

import pytest

from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    new_refresh_token,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("SuperSecure123!")
    assert verify_password("SuperSecure123!", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    uid = uuid.uuid4()
    token = create_access_token(uid)
    payload = decode_token(token)
    assert payload["sub"] == str(uid)
    assert payload["type"] == "access"


def test_refresh_token_unique():
    a = new_refresh_token()
    b = new_refresh_token()
    assert a[1] != b[1] and a[0] != b[0]


@pytest.mark.parametrize("text", ["hello", ""])
def test_local_embedder_deterministic(text):
    from app.services.embeddings import LocalHashingEmbeddings

    emb = LocalHashingEmbeddings(256)
    v1, v2 = emb.embed([text]), emb.embed([text])
    assert v1 == v2
    if text:
        assert abs(sum(x * x for x in v1[0]) - 1.0) < 0.01 or all(x == 0 for x in v1[0])
