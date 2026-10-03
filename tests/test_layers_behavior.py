"""Behavioral regression tests for the five student middleware layers."""

from types import SimpleNamespace

import pytest

from arena.corpus import Corpus, Doc, INJECTION_CANARY
from arena.model import DEGRADED_MARKERS, FINALIZE_SENTINEL
from arena.tools import ToolResult
from harness.agent import AgentContext
from harness.layers.budget_policy import BudgetPolicy
from harness.layers.citation_checker import CitationChecker
from harness.layers.critic import Critic
from harness.layers.injection_guard import (
    BLOCK_END, BLOCK_START, PLACEHOLDER, InjectionGuard,
)
from harness.layers.retry import Retry
from harness.middleware import MiddlewareStack


def context(docs=(), observations=(), limit=8, calls=0):
    return AgentContext(
        brief={"budget": {"max_tool_calls": limit}},
        tools=SimpleNamespace(calls=calls), trace=None,
        corpus=Corpus(list(docs)), observations=list(observations),
    )


def report(claims):
    return {"answer": "Model answer", "claims": claims,
            "citations": [], "abstain": False}


def test_critic_keeps_original_text_and_removes_fabrication():
    valid = {"text": "Delivery takes 24 hours.", "doc_id": "source-a"}
    result = Critic().after_agent(
        context(observations=[valid["text"]]),
        report([valid, {"text": "Invented statistic", "doc_id": "source-a"}]),
    )
    assert result["claims"] == [valid]
    assert result["claims"][0] is valid
    assert result["citations"] == ["source-a"]
    assert result["abstain"] is False


@pytest.mark.parametrize("claims", [None, {}, [], [None, {}, {"text": ""}],
                                        [{"text": "fiction"}]])
def test_critic_abstains_when_no_evidence_survives(claims):
    result = Critic().after_agent(context(), report(claims))
    assert result["abstain"] is True
    assert result["claims"] == result["citations"] == []
    assert "Không đủ căn cứ" in result["answer"]


def test_critic_splits_at_the_supported_conjunction_only():
    first = Doc(tags=(), doc_id="source-a", title="A", body="Alpha và Beta")
    second = Doc(tags=(), doc_id="source-b", title="B", body="Gamma")
    original = "Alpha và Beta và Gamma"
    result = Critic().after_agent(
        context([first, second], [first.body, second.body]),
        report([{"text": original, "doc_id": "wrong"}]),
    )
    assert result["claims"] == [
        {"text": first.body, "doc_id": first.doc_id},
        {"text": second.body, "doc_id": second.doc_id},
    ]
    assert all(c["text"] in original for c in result["claims"])
    assert result["abstain"] is True


def test_critic_does_not_split_using_unread_or_same_document():
    a = Doc(tags=(), doc_id="source-a", title="A", body="Alpha\nBeta")
    b = Doc(tags=(), doc_id="source-b", title="B", body="Unread header\nBeta")
    result = Critic().after_agent(
        context([a, b], [a.body]),
        report([{"text": "Alpha và Beta", "doc_id": a.doc_id}]),
    )
    assert result["claims"] == []


def test_citations_repair_only_from_fully_observed_sources():
    a = Doc(tags=(), doc_id="source-a", title="A", body="Header\nExact evidence line")
    b = Doc(tags=(), doc_id="source-b", title="B", body="Other evidence")
    claim = {"text": "Exact evidence", "doc_id": b.doc_id}
    result = CitationChecker().after_agent(context([a, b], [a.body]), report([claim]))
    assert result["claims"] == [{"text": "Exact evidence", "doc_id": a.doc_id}]
    assert result["citations"] == [a.doc_id]
    unread = {"text": "Exact evidence", "doc_id": b.doc_id}
    CitationChecker().after_agent(context([a, b], ["Exact evidence"]), report([unread]))
    assert unread["doc_id"] == b.doc_id


def test_citations_do_not_credit_cross_line_quotes_or_malformed_values():
    doc = Doc(tags=(), doc_id="source-a", title="A", body="First\nSecond")
    claim = {"text": doc.body, "doc_id": "wrong"}
    result = CitationChecker().after_agent(
        context([doc], [doc.body]), report([None, {"text": 42}, claim]),
    )
    assert claim["doc_id"] == "wrong"
    assert result["citations"] == ["wrong"]


@pytest.mark.parametrize("tail", [BLOCK_END + " safe suffix", ""])
def test_guard_quarantines_closed_and_truncated_blocks(tail):
    content = "safe prefix " + BLOCK_START + " " + INJECTION_CANARY + tail
    result = InjectionGuard().wrap_tool_call(
        context(), lambda *_: ToolResult(ok=True, content=content), "fetch_doc", {},
    )
    assert INJECTION_CANARY not in result.content
    assert BLOCK_START not in result.content
    assert PLACEHOLDER in result.content
    assert result.content.startswith("safe prefix ")
    if tail:
        assert result.content.endswith(" safe suffix")


def test_guard_handles_multiple_blocks_preserving_status_and_claims():
    block = BLOCK_START + INJECTION_CANARY + BLOCK_END
    original = ToolResult(ok=False, content=block + " middle " + block, error="timeout")
    result = InjectionGuard().wrap_tool_call(context(), lambda *_: original, "search", {})
    assert result.content.count(PLACEHOLDER) == 2
    assert result.ok is False and result.error == "timeout"
    claim = {"text": INJECTION_CANARY, "doc_id": "source-a"}
    final = report([claim])
    final["answer"] = "  " + INJECTION_CANARY + " safe " + INJECTION_CANARY
    InjectionGuard().after_agent(context(), final)
    assert final["answer"] == "safe"
    assert final["claims"] == [claim]


@pytest.mark.parametrize("limit,calls,spent", [(8, 6, False), (8, 7, True),
                                              (1, 0, True), (None, 100, False)])
def test_budget_reserves_submit_and_keeps_history(limit, calls, spent):
    ctx = context(limit=limit, calls=calls)
    messages = [{"role": "user", "content": "question"}]
    outgoing = BudgetPolicy().before_model(ctx, messages)
    assert len(messages) == 1
    assert (len(outgoing) == 2) is spent
    if spent:
        assert FINALIZE_SENTINEL in outgoing[-1]["content"]
    invoked = []
    result = BudgetPolicy().wrap_tool_call(
        ctx, lambda *args: invoked.append(args) or ToolResult(ok=True, content="ok"),
        "search", {"query": "question"},
    )
    assert bool(invoked) is not spent
    assert result.ok is not spent


@pytest.mark.parametrize("marker", DEGRADED_MARKERS)
def test_retry_recognizes_all_degraded_outputs(marker):
    ctx = context()
    invocations = []
    args = {"doc_id": "source-a"}

    def call(name, supplied):
        invocations.append((name, supplied))
        ctx.tools.calls += 1
        return ToolResult(ok=True, content=marker if len(invocations) == 1 else "clean")

    result = Retry().wrap_tool_call(ctx, call, "fetch_doc", args)
    assert result.content == "clean"
    assert invocations == [("fetch_doc", args)] * 2
    assert ctx.state["retry_attempts"] == 1


@pytest.mark.parametrize("limit,calls,expected", [(8, 6, 1), (None, 0, 3)])
def test_retry_is_bounded_and_reserves_submit(limit, calls, expected):
    ctx = context(limit=limit, calls=calls)
    failures = []

    def call(*_):
        ctx.tools.calls += 1
        result = ToolResult(ok=False, content="", error="timeout")
        failures.append(result)
        return result

    stack = MiddlewareStack([BudgetPolicy(), Retry()])
    result = stack.wrap_tool_call(ctx, call)("search", {})
    assert len(failures) == expected
    assert result is failures[-1]
    assert ctx.state["retry_attempts"] == expected - 1


def test_budget_blocks_retry_entirely_when_already_exhausted():
    ctx = context(calls=7)

    def forbidden(*_):
        pytest.fail("Tool call spent the submit reserve")

    result = MiddlewareStack([BudgetPolicy(), Retry()]).wrap_tool_call(ctx, forbidden)(
        "search", {},
    )
    assert result.ok is False
    assert ctx.tools.calls == 7
