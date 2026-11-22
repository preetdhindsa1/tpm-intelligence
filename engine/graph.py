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

import itertools
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

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


# --- Feature-to-feature dependencies (ADR-0013 addendum) ---------------------------------


@dataclass(frozen=True)
class StatedDependency:
    """A PR of ``downstream`` says it depends on a PR that only ``upstream`` owns."""

    upstream: str
    downstream: str
    blocker: str
    dependent: str


@dataclass(frozen=True)
class Coupling:
    """Two features tied by shared PRs and/or stated cross-feature dependencies.

    A shared PR means the same verified PR is listed for both features: shared code, not
    proof that one blocks the other. ``a < b`` so each pair appears once.
    """

    a: str
    b: str
    shared_prs: tuple[str, ...]
    stated: tuple[StatedDependency, ...]


@dataclass(frozen=True)
class WaitingPR:
    """An open PR that says it depends on a PR that has not merged."""

    pr: str
    waits_on: str
    waits_on_state: str  # open | closed (closed = never merged)
    features: tuple[str, ...]


@dataclass(frozen=True)
class FeatureDependencies:
    """How the given features depend on each other, from verified links and PR text."""

    couplings: tuple[Coupling, ...]
    clusters: tuple[tuple[str, ...], ...]  # connected groups (2+ features), largest first
    standalone: tuple[str, ...]  # features with no coupling
    waiting: tuple[WaitingPR, ...]
    sig_pairs: tuple[tuple[str, str, int], ...]  # (sig, sig, features owned by both)


def feature_dependencies(
    feature_prs: Mapping[str, Iterable[str]],
    feature_sigs: Mapping[str, Iterable[str]],
    pr_state: Mapping[str, str],
    pr_deps: Mapping[str, Iterable[str]],
) -> FeatureDependencies:
    """Couplings, clusters, waiting PRs and SIG pairs for a set of features.

    ``feature_prs`` maps feature key -> verified PR keys; ``pr_state`` gives each known PR's
    state (open | merged | closed); ``pr_deps`` maps PR key -> PR keys it says it depends
    on (:func:`pr_dependencies`). Deterministic: every output is sorted.
    """
    prs = {f: set(p) for f, p in feature_prs.items()}
    owners: dict[str, set[str]] = {}
    for f, keys in prs.items():
        for k in keys:
            owners.setdefault(k, set()).add(f)

    shared: dict[tuple[str, str], set[str]] = {}
    for pr, fs in owners.items():
        for a, b in itertools.combinations(sorted(fs), 2):
            shared.setdefault((a, b), set()).add(pr)

    stated: dict[tuple[str, str], set[StatedDependency]] = {}
    waiting: list[WaitingPR] = []
    for pr in sorted(owners):
        for dep in sorted(set(pr_deps.get(pr, ()))):
            for down in owners[pr]:
                for up in owners.get(dep, ()):
                    if up != down and dep not in prs[down]:
                        pair = (min(up, down), max(up, down))
                        stated.setdefault(pair, set()).add(StatedDependency(up, down, dep, pr))
            state = pr_state.get(dep)
            if pr_state.get(pr) == "open" and state is not None and state != "merged":
                waiting.append(WaitingPR(pr, dep, state, tuple(sorted(owners[pr]))))

    couplings = tuple(
        Coupling(
            a,
            b,
            tuple(sorted(shared.get((a, b), ()))),
            tuple(
                sorted(stated.get((a, b), ()), key=lambda d: (d.upstream, d.blocker, d.dependent))
            ),
        )
        for a, b in sorted(set(shared) | set(stated))
    )

    g: nx.Graph[str] = nx.Graph()
    g.add_edges_from((c.a, c.b) for c in couplings)
    clusters = tuple(
        sorted(
            (tuple(sorted(c)) for c in nx.connected_components(g)),
            key=lambda c: (-len(c), c),
        )
    )
    standalone = tuple(sorted(f for f in prs if f not in g))

    pairs: dict[tuple[str, str], int] = {}
    for f in prs:
        for a, b in itertools.combinations(sorted(set(feature_sigs.get(f, ()))), 2):
            pairs[(a, b)] = pairs.get((a, b), 0) + 1
    sig_pairs = tuple(
        sorted(((a, b, n) for (a, b), n in pairs.items()), key=lambda t: (-t[2], t[0], t[1]))
    )
    return FeatureDependencies(couplings, clusters, standalone, tuple(waiting), sig_pairs)
