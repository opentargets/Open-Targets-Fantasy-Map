from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Assignment:
    disease_id: str
    path: tuple[str, ...]
    state_id: str
    province_id: str
    extra_parents: tuple[str, ...]


class OntologyResolver:
    def __init__(
        self,
        disease_ids: list[str],
        edges: list[dict[str, Any]],
        child_col: str,
        parent_col: str,
        *,
        root_ids: list[str] | None = None,
        skip_roots: bool = True,
    ) -> None:
        self.disease_ids = sorted({str(d).strip() for d in disease_ids if str(d).strip()})
        self.parents: dict[str, set[str]] = {d: set() for d in self.disease_ids}
        self.children: dict[str, set[str]] = {}
        self.root_ids = {str(r).strip() for r in (root_ids or []) if str(r).strip()}
        self.skip_roots = skip_roots

        for row in edges:
            child = str(row.get(child_col, "")).strip()
            parent = str(row.get(parent_col, "")).strip()
            if not child or not parent or child == parent:
                continue
            self.parents.setdefault(child, set()).add(parent)
            self.parents.setdefault(parent, set())
            self.children.setdefault(parent, set()).add(child)
            self.children.setdefault(child, set())

        self.roots = {node for node, parents in self.parents.items() if not parents} | self.root_ids
        self._descendant_count_cache: dict[str, int] = {}
        self._path_cache: dict[str, tuple[str, ...]] = {}

    def assign_all(self) -> dict[str, Assignment]:
        return {disease_id: self.assign(disease_id) for disease_id in self.disease_ids}

    def assign(self, disease_id: str) -> Assignment:
        path = self.primary_path(disease_id)
        meaningful = path
        if self.skip_roots and len(path) > 1 and path[0] in self.roots:
            meaningful = path[1:]

        state_id = meaningful[0] if meaningful else disease_id
        province_id = meaningful[1] if len(meaningful) > 1 else disease_id
        primary_parent = path[-2] if len(path) > 1 else None
        extra_parents = tuple(sorted(parent for parent in self.parents.get(disease_id, set()) if parent != primary_parent))

        return Assignment(
            disease_id=disease_id,
            path=path,
            state_id=state_id,
            province_id=province_id,
            extra_parents=extra_parents,
        )

    def primary_path(self, node: str) -> tuple[str, ...]:
        if node in self._path_cache:
            return self._path_cache[node]
        path = self._primary_path(node, visiting=set())
        self._path_cache[node] = path
        return path

    def _primary_path(self, node: str, visiting: set[str]) -> tuple[str, ...]:
        if node in visiting:
            return (node,)
        parents = sorted(self.parents.get(node, set()))
        if not parents or node in self.root_ids:
            return (node,)

        visiting.add(node)
        candidates: list[tuple[int, int, tuple[str, ...], str]] = []
        for parent in parents:
            parent_path = self._primary_path(parent, visiting)
            candidate = parent_path + (node,)
            candidates.append((-self.descendant_count(parent), len(candidate), candidate, parent))
        visiting.remove(node)

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][2]

    def descendant_count(self, node: str) -> int:
        if node in self._descendant_count_cache:
            return self._descendant_count_cache[node]
        seen: set[str] = set()
        stack = list(self.children.get(node, set()))
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            stack.extend(self.children.get(child, set()))
        self._descendant_count_cache[node] = len(seen)
        return len(seen)
