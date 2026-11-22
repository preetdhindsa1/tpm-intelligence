"""Feature-to-feature dependencies (engine/graph.py), on real-shaped v1.38 keys."""

from __future__ import annotations

from engine.graph import StatedDependency, feature_dependencies

ENH = "kubernetes/enhancements"
KK = "kubernetes/kubernetes"
F3157, F6268, F6404, F6395, F2570 = (f"{ENH}#{n}" for n in (3157, 6268, 6404, 6395, 2570))


def pr(n: int) -> str:
    return f"{KK}#{n}"


def test_stated_dependency_between_features_has_a_direction() -> None:
    # Real v1.38 shape: #143270 (KEP #3157) says it depends on #143232 (KEP #6268), and
    # #143276 (KEP #6404) depends on #143270.
    deps = feature_dependencies(
        feature_prs={F6268: [pr(143232)], F3157: [pr(143270)], F6404: [pr(143276)]},
        feature_sigs={},
        pr_state={pr(143232): "merged", pr(143270): "merged", pr(143276): "merged"},
        pr_deps={pr(143270): [pr(143232)], pr(143276): [pr(143270)]},
    )
    assert [(c.a, c.b) for c in deps.couplings] == [(F3157, F6268), (F3157, F6404)]
    assert deps.couplings[0].stated == (StatedDependency(F6268, F3157, pr(143232), pr(143270)),)
    assert deps.couplings[0].shared_prs == ()
    assert deps.clusters == ((F3157, F6268, F6404),)
    assert deps.standalone == ()
    assert deps.waiting == ()


def test_shared_prs_couple_features_and_standalone_features_are_listed() -> None:
    deps = feature_dependencies(
        feature_prs={F6395: [pr(143709), pr(1)], F2570: [pr(1)], F3157: [pr(2)]},
        feature_sigs={},
        pr_state={},
        pr_deps={},
    )
    assert len(deps.couplings) == 1
    assert deps.couplings[0].shared_prs == (pr(1),)
    assert deps.clusters == ((F2570, F6395),)
    assert deps.standalone == (F3157,)


def test_a_dependency_inside_one_feature_is_not_a_coupling() -> None:
    # Both PRs belong to #6395 (and the blocker to #2570 too): no stated cross-feature edge,
    # only the shared PR.
    deps = feature_dependencies(
        feature_prs={F6395: [pr(143445), pr(143709)], F2570: [pr(143445)]},
        feature_sigs={},
        pr_state={pr(143445): "merged", pr(143709): "open"},
        pr_deps={pr(143709): [pr(143445)]},
    )
    (c,) = deps.couplings
    assert c.shared_prs == (pr(143445),)
    assert c.stated == ()


def test_open_pr_waiting_on_unmerged_or_closed_pr() -> None:
    # Real v1.38 shape: #141452 (open) depends on #141450, which was closed without merging.
    deps = feature_dependencies(
        feature_prs={f"{ENH}#6268": [pr(141450), pr(141451), pr(141452)]},
        feature_sigs={},
        pr_state={pr(141450): "closed", pr(141451): "merged", pr(141452): "open"},
        pr_deps={pr(141452): [pr(141450)], pr(141451): [pr(141450)]},
    )
    (w,) = deps.waiting
    assert (w.pr, w.waits_on, w.waits_on_state) == (pr(141452), pr(141450), "closed")
    assert w.features == (f"{ENH}#6268",)


def test_dependency_on_an_unknown_pr_is_ignored() -> None:
    deps = feature_dependencies(
        feature_prs={F6395: [pr(1)]},
        feature_sigs={},
        pr_state={pr(1): "open"},
        pr_deps={pr(1): [pr(999)]},
    )
    assert deps.waiting == ()
    assert deps.couplings == ()


def test_sig_pairs_count_features_owned_by_both_sigs() -> None:
    deps = feature_dependencies(
        feature_prs={F6395: [], F2570: [], F3157: []},
        feature_sigs={
            F6395: ["sig/node", "sig/storage"],
            F2570: ["sig/node"],
            F3157: ["sig/api-machinery", "sig/node", "sig/storage"],
        },
        pr_state={},
        pr_deps={},
    )
    assert deps.sig_pairs[0] == ("sig/node", "sig/storage", 2)
    assert ("sig/api-machinery", "sig/node", 1) in deps.sig_pairs
