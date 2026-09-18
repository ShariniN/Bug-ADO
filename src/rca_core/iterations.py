from __future__ import annotations


def _day(value: str | None) -> str | None:
    return value[:10] if value else None


def current_pi(tree: dict, today: str, pi_depth: int = 1) -> str | None:
    """Work-item-style path of the PI containing `today` (YYYY-MM-DD), e.g. 'Acme\\PI-14'.
    The shallowest dated node at depth >= pi_depth wins; a dated sprint under an undated PI still yields the PI."""
    best: tuple[int, list[str]] | None = None

    def walk(node: dict, names: list[str], depth: int) -> None:
        nonlocal best
        attrs = node.get("attributes") or {}
        start, finish = _day(attrs.get("startDate")), _day(attrs.get("finishDate"))
        if depth >= pi_depth and start and finish and start <= today <= finish and (best is None or depth < best[0]):
            best = (depth, names)
        for child in node.get("children") or []:
            walk(child, names + [child["name"]], depth + 1)

    walk(tree, [tree.get("name", "")], 0)
    return "\\".join(best[1][: pi_depth + 1]) if best else None
