"""JSON canónico, digest y vectores compartidos con P3 (WAL-P1-001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from support.fakes import CAPABILITY_SECRET

from wallba.contracts.canonical import (
    CanonicalizationError,
    CanonicalRequest,
    canonical_json,
    loads_strict,
    sha256_hex,
)
from wallba.contracts.capability import Capability, capability_signing_bytes, compute_signature

VECTORS = Path(__file__).resolve().parents[2] / "contracts" / "examples" / "canonical_vectors.json"


def test_keys_are_sorted_recursively_without_whitespace() -> None:
    assert canonical_json({"b": 1, "a": {"d": [True, None], "c": "ñ"}}) == (
        '{"a":{"c":"ñ","d":[true,null]},"b":1}'.encode()
    )


@pytest.mark.parametrize("value", [1.5, {"a": float("nan")}, ["é"], {1: "x"}])
def test_non_canonical_values_are_rejected(value: object) -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json(value)


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":1.5}', '{"a":NaN}', '{"a":Infinity}'])
def test_strict_loader_rejects_ambiguous_json(raw: str) -> None:
    with pytest.raises(CanonicalizationError):
        loads_strict(raw)


def test_shared_vectors_match_implementation() -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    request = CanonicalRequest.model_validate(vectors["canonical_request"])
    assert request.canonical_bytes().decode("utf-8") == vectors["canonical_bytes"]
    assert request.digest() == vectors["request_digest"]
    assert request.digest() == sha256_hex(vectors["canonical_bytes"].encode("utf-8"))

    capability = Capability.model_validate(vectors["capability"])
    signing = capability_signing_bytes(capability)
    assert signing.decode("utf-8") == vectors["capability_signing_bytes"]
    assert compute_signature(signing, vectors["test_secret"].encode("utf-8")) == capability.signature


def test_vector_secret_is_a_test_value() -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert vectors["test_secret"].startswith("test-only-")
    assert vectors["test_secret"].encode() != CAPABILITY_SECRET
