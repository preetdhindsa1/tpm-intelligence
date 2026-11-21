"""Dependency graph and critical path (NetworkX). Pure, no I/O.

Nodes: the release, its features, and PRs. Edges:

* ``release -> feature`` (contains)
* ``feature -> PR`` (implemented by; verified links only)
* ``PR A -> PR B`` when B's text says it depends on A ("depends on #A", "blocked by #A",
  "on top of #A", "builds on #A", "follow-up to #A", "/hold until #A")

KEPs have no machine-readable dependency field, so for most features the critical path is
one or two PRs. We report what the data shows, nothing deeper.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping

import networkx as nx

from engine.projection import Feature, PullRequest

_DEPENDS = re.compile(
    r"(?:depends\s+on|blocked\s+by|requires|on\s+top\s+of|builds\s+on|follow[- ]?up\s+(?:to|of|on)"
    r"|/hold\s+until)\s+(?:https://github\.com/(?P<repo>[\w.-]+/[\w.-]+)/pull/|#)(?P<n>\d+)",
    re.I,
)


def pr_dependencies(pr: PullRequest) -> list[str]:
    """Keys of PRs that ``pr`` says must merge first (same repo for ``#N`` references)."""
    out: list[str] = []
    for m in _DEPENDS.finditer(f"{pr.title}\n{pr.body}"):
        key = f"{m.group('repo') or pr.repo}#{m.group('n')}"
        if key != pr.key and key not in out:
            out.append(key)
    return out


def build_graph(
    release_key: str,
    features: Iterable[Feature],
    pull_requests: Mapping[str, PullRequest],
    links: Mapping[str, Iterable[str]],
) -> nx.DiGraph[str]:
    """Build the release graph. ``links`` maps feature key -> verified PR keys."""
    g: nx.DiGraph[str] = nx.DiGraph()
    g.add_node(release_key, kind="release")
    for f in features:
        g.add_node(f.key, kind="feature")
        g.add_edge(release_key, f.key, kind="contains")
        for pr_key in links.get(f.key, ()):
            if pr_key in pull_requests:
                g.add_node(pr_key, kind="pull_request")
                g.add_edge(f.key, pr_key, kind="implemented_by")
    for pr in pull_requests.values():
        if pr.key not in g:
            continue
        for dep in pr_dependencies(pr):
            if dep in pull_requests:
                g.add_node(dep, kind="pull_request")
                g.add_edge(dep, pr.key, kind="blocks")
    return g


def critical_path(
    g: nx.DiGraph[str],
    feature_key: str,
    pull_requests: Mapping[str, PullRequest],
    weight: Callable[[PullRequest], float] = lambda pr: 1.0,
) -> list[str]:
    """Longest chain of **unmerged** PRs the feature still needs, in merge order.

    ``weight`` is the expected remaining time per PR (1.0 per PR until the forecast
    supplies durations). Cycles in stated dependencies are broken deterministically.
    """
    if feature_key not in g:
        return []
    open_prs = {
        k for k in g.successors(feature_key) if k in pull_requests and pull_requests[k].is_open
    }
    # Include open prerequisites that are not themselves linked to the feature.
    frontier = list(open_prs)
    while frontier:
        node = frontier.pop()
        for dep in g.predecessors(node):
            if (
                g.nodes[dep].get("kind") == "pull_request"
                and dep not in open_prs
                and (dep in pull_requests and pull_requests[dep].is_open)
            ):
                open_prs.add(dep)
                frontier.append(dep)
    if not open_prs:
        return []

    sub: nx.DiGraph[str] = nx.DiGraph()
    sub.add_nodes_from(sorted(open_prs))
    sub.add_edges_from(
        (u, v)
        for u, v, d in g.edges(data=True)
        if d.get("kind") == "blocks" and u in open_prs and v in open_prs
    )
    while not nx.is_directed_acyclic_graph(sub):
        cycle = nx.find_cycle(sub)
        sub.remove_edge(*sorted(cycle)[-1][:2])

    best: dict[str, tuple[float, list[str]]] = {}
    for node in nx.lexicographical_topological_sort(sub):
        own = weight(pull_requests[node])
        prev = [best[p] for p in sub.predecessors(node)]
        base = max(prev, key=lambda t: t[0]) if prev else (0.0, [])
        best[node] = (base[0] + own, [*base[1], node])
    # Ties resolve to the first path in lexicographic topological order (deterministic).
    return max(best.values(), key=lambda t: t[0])[1]
