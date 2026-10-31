"""Carga YAML/JSON acotada. No resuelve alias, tags ni documentos múltiples."""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

from wallba.policy.models import PolicyFieldError
from wallba.policy.schemas import (
    MAX_COLLECTION,
    MAX_DEPTH,
    MAX_DOCUMENT_BYTES,
    MAX_STRING_LENGTH,
    ValidationReport,
    validate_mapping,
)

_ALLOWED_TAGS = frozenset(
    {
        "tag:yaml.org,2002:str",
        "tag:yaml.org,2002:int",
        "tag:yaml.org,2002:bool",
        "tag:yaml.org,2002:null",
        "tag:yaml.org,2002:seq",
        "tag:yaml.org,2002:map",
    }
)


class _StructureReject(Exception):
    def __init__(self, code: str, field: str = "$") -> None:
        self.code = code
        self.field = field
        super().__init__(code)


class StrictLoader(yaml.SafeLoader):
    """Loader sin resolvers heredados: solo bool, null y enteros acotados."""


StrictLoader.yaml_implicit_resolvers = {}
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))
StrictLoader.add_implicit_resolver("tag:yaml.org,2002:null", re.compile(r"^(?:null|~)$"), list("n~"))
StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^(?:0|-?[1-9][0-9]{0,17})$"),
    list("-0123456789"),
)


def _compose(self: StrictLoader, parent: Any, index: Any) -> Any:
    if self.check_event(yaml.events.AliasEvent):
        raise _StructureReject("alias_rejected")
    event = self.peek_event()
    if getattr(event, "anchor", None):
        raise _StructureReject("alias_rejected")
    node = yaml.SafeLoader.compose_node(self, parent, index)
    if getattr(node, "tag", None) not in _ALLOWED_TAGS:
        raise _StructureReject("tag_rejected")
    return node


def _construct_mapping(self: StrictLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[str, Any]:
    if not isinstance(node, yaml.MappingNode):
        raise _StructureReject("type")
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, yaml.ScalarNode) or key_node.tag != "tag:yaml.org,2002:str":
            raise _StructureReject("type")
        key = self.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise _StructureReject("type")
        if key in mapping:
            raise _StructureReject("duplicate_key")
        mapping[key] = self.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.compose_node = _compose  # type: ignore[method-assign]
StrictLoader.construct_mapping = _construct_mapping  # type: ignore[method-assign]


def load_policy(content: str | bytes, format: str) -> ValidationReport:
    """Convierte un documento a modelo validado. No activa ni ejecuta herramientas."""

    try:
        if format not in {"yaml", "json"}:
            raise _StructureReject("invalid_value", "format")
        text = _as_text(content)
        data = _parse_yaml(text) if format == "yaml" else _parse_json(text)
        _walk(data, "$", 1)
    except _StructureReject as exc:
        return _invalid(exc.field, exc.code)
    except yaml.YAMLError as exc:
        code = "multiple_documents" if "another document" in str(exc) else "invalid_syntax"
        return _invalid("$", code)
    except json.JSONDecodeError:
        return _invalid("$", "invalid_syntax")
    if not isinstance(data, dict):
        return _invalid("$", "type")
    return validate_mapping(data)


def _as_text(content: str | bytes) -> str:
    if isinstance(content, bytes):
        if content.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
            raise _StructureReject("unsupported_type")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _StructureReject("unsupported_type") from exc
    elif isinstance(content, str):
        if content.startswith("\ufeff"):
            raise _StructureReject("unsupported_type")
        text = content
    else:
        raise _StructureReject("type")
    if "\x00" in text:
        raise _StructureReject("unsupported_type")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _StructureReject("max_bytes")
    if not text.strip():
        raise _StructureReject("invalid_value")
    return text


def _parse_yaml(text: str) -> Any:
    loader = StrictLoader(text)
    try:
        node = loader.get_single_node()
        if node is None:
            raise _StructureReject("invalid_value")
        return loader.construct_document(node)
    finally:
        loader.dispose()


def _parse_json(text: str) -> Any:
    def pairs(items: list[tuple[Any, Any]]) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for key, value in items:
            if not isinstance(key, str):
                raise _StructureReject("type")
            if key in mapping:
                raise _StructureReject("duplicate_key")
            mapping[key] = value
        return mapping

    def reject_constant(_name: str) -> Any:
        raise _StructureReject("unsupported_type")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)


def _walk(value: object, path: str, depth: int) -> None:
    if depth > MAX_DEPTH:
        raise _StructureReject("max_depth", path)
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > 10**18:
            raise _StructureReject("out_of_range", path)
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH or "\x00" in value:
            raise _StructureReject("max_length", path)
        return
    if isinstance(value, float):
        raise _StructureReject("unsupported_type", path)
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION:
            raise _StructureReject("max_items", path)
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_COLLECTION:
            raise _StructureReject("max_items", path)
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_STRING_LENGTH:
                raise _StructureReject("invalid_value", path)
            child = key if path == "$" else f"{path}.{key}"
            _walk(item, child, depth + 1)
        return
    raise _StructureReject("unsupported_type", path)


def _invalid(field: str, code: str) -> ValidationReport:
    return ValidationReport(False, (PolicyFieldError(field=field or "$", code=code),), None)
