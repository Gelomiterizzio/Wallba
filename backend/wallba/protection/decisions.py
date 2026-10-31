"""Efecto de las políticas sobre una operación concreta."""

from __future__ import annotations

READ = "read"
WRITE_OPS = frozenset({"write", "delete", "rename"})
OBSERVE = frozenset({"monitor", "alert"})
PREVENTIVE = frozenset({"block_read", "block_write", "block_all"})


def blocks(policy: str, operation: str) -> bool:
    if policy in OBSERVE:
        return False
    if policy == "block_read":
        return operation == READ
    if policy == "block_write":
        return operation in WRITE_OPS
    if policy == "block_all":
        return operation in WRITE_OPS or operation == READ
    return True


def strictest(policies: list[str]) -> str:
    blocks_read = any(blocks(policy, READ) for policy in policies)
    blocks_write = any(blocks(policy, "write") for policy in policies)
    if blocks_read and blocks_write:
        return "block_all"
    if blocks_write:
        return "block_write"
    if blocks_read:
        return "block_read"
    if "alert" in policies:
        return "alert"
    if policies:
        return "monitor"
    return "monitor"


def is_excluded(path: str, exclusions: set[str]) -> bool:
    for excluded in exclusions:
        if path == excluded or path.startswith(excluded + "/"):
            return True
    return False
