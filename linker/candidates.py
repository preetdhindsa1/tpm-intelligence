"""Shortlist the features an unlinked PR might belong to (ADR-0011). Pure, no I/O.

The AI link suggester may only pick from this shortlist, so it can never name a feature
that is not in the release. Scoring is plain word overlap, weighted so that rare words
(``ephemeral``, ``podgroup``) count more than common ones (``pod``, ``api``):

* **Feature text:** title, the KEP's one-line description, the words of its KEP folder
  name and its feature-gate names split at capitals (``DynamicNodeLocalEphemeralVolumes``
  gives ``dynamic node local ephemeral volumes``).
* **PR text:** title (counted twice), body without HTML comments, URLs or the PR
  template's fixed headings.
* **SIG overlap** adds a bonus. It never puts a feature on the list on its own.

Shortlist recall is measured by the hidden-key eval (``evals/link_suggester.py``).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

SHORTLIST_SIZE = 12
SIG_BONUS = 1.0
TITLE_WEIGHT = 2

_COMMENTS = re.compile(r"<!--.*?-->", re.S)
_URL = re.compile(r"https?://\S+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]+")
_ONE_LINE = re.compile(r"one-line enhancement description[^:]*:\s*(.+)", re.I)
_KEP_DIR = re.compile(r"keps/[\w-]+/\d+-([\w-]+)")

# Words that appear in almost every PR or KEP and carry no signal about which feature.
STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "into",
        "when",
        "not",
        "are",
        "was",
        "were",
        "will",
        "can",
        "has",
        "have",
        "had",
        "but",
        "all",
        "any",
        "its",
        "use",
        "used",
        "using",
        "via",
        "add",
        "adds",
        "added",
        "remove",
        "removes",
        "removed",
        "update",
        "updates",
        "updated",
        "fix",
        "fixes",
        "fixed",
        "support",
        "supports",
        "make",
        "makes",
        "new",
        "also",
        "only",
        "more",
        "than",
        "then",
        "should",
        "would",
        "could",
        "does",
        "did",
        "done",
        "which",
        "what",
        "who",
        "how",
        "why",
        "where",
        "there",
        "their",
        "them",
        "they",
        "our",
        "you",
        "your",
        "please",
        "see",
        "none",
        "yes",
        "pull",
        "request",
        "kind",
        "feature",
        "release",
        "note",
        "notes",
        "kubernetes",
        "k8s",
        "pr",
        "prs",
        "kep",
        "keps",
        "issue",
        "issues",
        "test",
        "tests",
        "testing",
        "type",
        "user",
        "facing",
        "change",
        "changes",
        "introduce",
        "description",
        "additional",
        "documentation",
        "docs",
        "link",
        "links",
        "enhancement",
        "enhancements",
        "alpha",
        "beta",
        "stable",
        "ga",
        "sig",
        "code",
        "main",
        "implement",
        "implements",
        "implementation",
        "tracking",
        "one",
        "line",
        "proposal",
        "readme",
        "md",
        "github",
        "com",
    }
)

# Lines of the kubernetes/kubernetes PR template that every PR repeats.
_TEMPLATE_LINES = re.compile(
    r"^\s*(#+\s*(what type of pr is this|what this pr does|which issue|special notes"
    r"|does this pr introduce|additional documentation)|/kind\b|```)",
    re.I,
)


def words(text: str) -> list[str]:
    """Lower-case words of 3+ characters, CamelCase split, stopwords removed."""
    out: list[str] = []
    for raw in _WORD.findall(text):
        for part in _CAMEL.split(raw):
            w = part.lower()
            if len(w) >= 3 and w not in STOPWORDS:
                out.append(w)
    return out


def pr_text(title: str, body: str) -> str:
    """PR text as the suggester and the scorer see it: no comments, URLs or template lines."""
    lines = [
        line
        for line in _URL.sub(" ", _COMMENTS.sub("", body or "")).splitlines()
        if not _TEMPLATE_LINES.match(line)
    ]
    return "\n".join([title, *lines]).strip()


def one_line_description(description: str) -> str:
    """The KEP issue's "One-line enhancement description" line, if present."""
    m = _ONE_LINE.search(description or "")
    return m.group(1).strip() if m else ""


@dataclass(frozen=True)
class FeatureDoc:
    """What a feature offers for matching (and what the suggester is shown)."""

    key: str
    title: str
    summary: str  # one-line description
    feature_gates: tuple[str, ...]
    sigs: tuple[str, ...]
    stage: str | None = None

    @classmethod
    def build(
        cls,
        key: str,
        title: str,
        description: str,
        feature_gates: Iterable[str] = (),
        labels: Iterable[str] = (),
        stage: str | None = None,
    ) -> FeatureDoc:
        """From a work item's fields."""
        return cls(
            key=key,
            title=title,
            summary=one_line_description(description),
            feature_gates=tuple(feature_gates),
            sigs=tuple(sorted(lb for lb in labels if lb.startswith("sig/"))),
            stage=stage,
        )

    def terms(self, description: str = "") -> Counter[str]:
        """Bag of words for scoring."""
        folder = " ".join(m.replace("-", " ") for m in _KEP_DIR.findall(description))
        text = " ".join([self.title, self.summary, folder, *self.feature_gates])
        return Counter(words(text))


@dataclass(frozen=True)
class Candidate:
    """One shortlisted feature with its score and the shared words behind it."""

    feature: FeatureDoc
    rank: int  # 1 = best
    score: float
    shared_words: tuple[str, ...]
    shared_sigs: tuple[str, ...]


@dataclass(frozen=True)
class CandidateIndex:
    """Feature term bags plus inverse document frequencies, built once per release."""

    docs: Mapping[str, FeatureDoc]
    terms: Mapping[str, Counter[str]]
    idf: Mapping[str, float]

    @classmethod
    def build(cls, features: Iterable[tuple[FeatureDoc, str]]) -> CandidateIndex:
        """``features`` are (doc, raw description) pairs."""
        docs: dict[str, FeatureDoc] = {}
        terms: dict[str, Counter[str]] = {}
        for doc, description in features:
            docs[doc.key] = doc
            terms[doc.key] = doc.terms(description)
        df: Counter[str] = Counter()
        for bag in terms.values():
            df.update(bag.keys())
        n = max(len(terms), 1)
        idf = {t: math.log(1 + n / d) for t, d in df.items()}
        return cls(docs=docs, terms=terms, idf=idf)


def strip_link_evidence(text: str, numbers: Iterable[int], gates: Iterable[str]) -> str:
    """Remove what the deterministic rules link on: KEP references and gate names.

    Used by the hidden-key eval: a PR that rules linked, with its keys removed, stands in
    for an unlinked PR whose right answer is known.
    """
    from linker.refs import _REF

    out = _URL.sub(" ", text)
    out = _REF.sub(" ", out)
    for n in sorted(set(numbers), reverse=True):
        out = re.sub(rf"#{n}(?!\d)", " ", out)
    for gate in sorted(set(gates), key=len, reverse=True):
        out = re.sub(rf"(?<!\w){re.escape(gate)}(?!\w)", " ", out)
    return out


def shortlist(
    title: str,
    body: str,
    labels: Sequence[str],
    index: CandidateIndex,
    *,
    size: int = SHORTLIST_SIZE,
) -> list[Candidate]:
    """Best ``size`` features by weighted word overlap; features sharing no word are left out."""
    bag: Counter[str] = Counter()
    for _ in range(TITLE_WEIGHT):
        bag.update(words(title))
    bag.update(words(pr_text("", body)))
    pr_sigs = {lb for lb in labels if lb.startswith("sig/")}
    scored: list[tuple[float, str, tuple[str, ...], tuple[str, ...]]] = []
    for key, fterms in index.terms.items():
        shared = sorted(set(bag) & set(fterms))
        if not shared:
            continue
        score = sum(index.idf[t] * math.log1p(bag[t]) for t in shared)
        sigs = tuple(sorted(pr_sigs & set(index.docs[key].sigs)))
        if sigs:
            score += SIG_BONUS
        scored.append((score, key, tuple(shared), sigs))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [
        Candidate(index.docs[key], rank, round(score, 3), shared, sigs)
        for rank, (score, key, shared, sigs) in enumerate(scored[:size], start=1)
    ]
