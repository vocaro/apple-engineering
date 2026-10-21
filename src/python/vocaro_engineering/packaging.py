"""SwiftPM target closure and canonical dependency helpers."""
from __future__ import annotations

def target_dependencies(target: dict) -> list[str]:
    result = []
    for dependency in target["dependencies"]:
        if "byName" in dependency:
            result.append(dependency["byName"][0])
        elif "target" in dependency:
            result.append(dependency["target"][0])
        else:
            raise ValueError(f'{target["name"]}: portable core must use canonical target dependencies')
    return result

def target_closure(targets: dict, name: str) -> set[str]:
    """`name` and every target of this package it depends on, directly or not."""
    closure, pending = set(), [name]
    while pending:
        current = pending.pop()
        if current in closure or current not in targets:
            continue
        closure.add(current)
        for dependency in targets[current]["dependencies"]:
            for kind in ("byName", "target"):
                if kind in dependency:
                    pending.append(dependency[kind][0])
    return closure
