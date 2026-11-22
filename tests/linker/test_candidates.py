"""Shortlist and hidden-key helpers, with real-shaped #6395 text (ADR-0011)."""

from __future__ import annotations

from linker.candidates import (
    CandidateIndex,
    FeatureDoc,
    one_line_description,
    pr_text,
    shortlist,
    strip_link_evidence,
    words,
)

DESC_6395 = (
    "### Enhancement Description\n"
    "- One-line enhancement description (can be used as a release note): Support "
    "dynamically adding and removing node-local ephemeral volumes (ConfigMaps, Secrets, "
    "Projected, EmptyDir) to existing pods.\n"
    "- Kubernetes Enhancement Proposal: https://github.com/kubernetes/enhancements/blob/"
    "master/keps/sig-storage/6395-dynamic-node-local-ephemeral-volumes/README.md\n"
)
F6395 = FeatureDoc.build(
    "kubernetes/enhancements#6395",
    "Dynamic node-local ephemeral volumes",
    DESC_6395,
    ["DynamicNodeLocalEphemeralVolumes"],
    ["sig/node", "sig/storage", "tracked/yes"],
    "alpha",
)
F2570 = FeatureDoc.build(
    "kubernetes/enhancements#2570",
    "Support Memory QoS with cgroups v2",
    "",
    ["MemoryQoS"],
    ["sig/node"],
    "beta",
)
INDEX = CandidateIndex.build([(F6395, DESC_6395), (F2570, "")])


def test_words_split_camel_case_and_drop_stopwords() -> None:
    assert words("DynamicNodeLocalEphemeralVolumes for the PR") == [
        "dynamic",
        "node",
        "local",
        "ephemeral",
        "volumes",
    ]


def test_pr_text_drops_comments_urls_and_template_headings() -> None:
    body = (
        "<!-- Thanks for sending a pull request! -->\n#### What type of PR is this?\n"
        "/kind feature\nAdds volume hot-plug. See https://example.com/x\n"
    )
    text = pr_text("kubelet: hot-plug volumes", body)
    assert "Thanks" not in text
    assert "What type" not in text
    assert "/kind" not in text
    assert "https://" not in text
    assert "Adds volume hot-plug." in text


def test_one_line_description_and_feature_doc() -> None:
    assert one_line_description(DESC_6395).startswith("Support dynamically adding")
    assert F6395.sigs == ("sig/node", "sig/storage")


def test_shortlist_ranks_the_matching_feature_first() -> None:
    found = shortlist("kubelet: mount ephemeral volumes into running pods", "", [], INDEX)
    assert [c.feature.key for c in found][:1] == ["kubernetes/enhancements#6395"]
    assert found[0].rank == 1
    assert "ephemeral" in found[0].shared_words


def test_sig_overlap_alone_never_shortlists() -> None:
    assert shortlist("bump golang.org/x/net", "", ["sig/node"], INDEX) == []


def test_shortlist_size_limit() -> None:
    assert len(shortlist("node volumes memory cgroups", "", [], INDEX, size=1)) == 1


def test_strip_link_evidence_removes_keys_and_gates() -> None:
    text = (
        "KEP-6395: wire DynamicNodeLocalEphemeralVolumes\nPart of #6395 and "
        "https://github.com/kubernetes/enhancements/issues/6395, not #63950"
    )
    out = strip_link_evidence(text, [6395], ["DynamicNodeLocalEphemeralVolumes"])
    assert "6395" not in out.replace("63950", "")
    assert "DynamicNodeLocalEphemeralVolumes" not in out
    assert "#63950" in out
    assert "wire" in out
