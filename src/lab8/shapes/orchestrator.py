"""Shape C — orchestrator plus read-only investigators. Student work.

1. Build a handoff with `lab8.handoff.make_handoff`. Allowed tools are read-only.
   Never put parent_secret, raw headers, or the full claim row into facts.
2. `lab8.runtime.run_readonly_investigators` runs those tools.
3. The orchestrator quotes from the investigator's order view and calls
   `durability.issue_refund`. Investigators have no write registry.
   Pass the full quote; the host subtracts earlier refunds on the same order.
   `lookup_refund_history` is a read-only tool you may hand to an investigator.
4. Trace the sanitized handoff, not the parent context.

An LLM summary of the parent context is not a sanitizer. Use the allowlist.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.handoff import make_handoff
from lab8.mock_llm import complete
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import get_claim_view, tool_cost
from lab8.trace import Trace

SHAPE = "orchestrator"

# The investigator's whole world. lookup_order must come before
# compute_compensation: the runner quotes from the order view it just fetched.
INVESTIGATOR_TOOLS = ["lookup_order", "lookup_refund_history", "compute_compensation"]


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(
    conn: sqlite3.Connection,
    claim_id: str,
    *,
    seed: int,
    crash_at: str | None,
) -> RunResult:
    budget = Budget()
    run_id = make_run_id(SHAPE, claim_id, seed)
    trace = Trace(run_id)

    def done(status: str, proposal: int, reason: str | None) -> RunResult:
        return finish(
            conn,
            shape=SHAPE,
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    # The orchestrator reads the claim through the allowlisted view. The raw row
    # carries parent_secret and raw_headers, and neither may cross the handoff.
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim.get("found"):
        trace.add("error", {"reason": "unknown_claim"})
        return done("failed", 0, "unknown_claim")

    if not claim.get("order_id"):
        complete(budget, seed=seed, purpose="draft", prompt=f"needs_info:{claim_id}")
        trace.add("decision", {"status": "needs_info", "reason": "missing_order_id"})
        return done("needs_info", 0, "missing_order_id")

    # The handoff is built by an allowlist in code, never by summarising the
    # parent context with a model. `facts` stays empty: the investigator reads
    # what it needs inside its own principal scope, so nothing from the claim
    # row has to travel at all. make_handoff drops every key outside
    # ALLOWED_FIELDS, refuses a write tool, and raises if a canary survives.
    complete(budget, seed=seed, purpose="plan", prompt=f"delegate:{claim_id}")
    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="check_applicable_policy",
        facts={},
        allowed_tools=INVESTIGATOR_TOOLS,
    )
    trace.add("handoff", safe_dump(handoff))

    # Investigators run with worker=True inside the runner, so they can only
    # reach read tools. They have no write registry at all.
    try:
        investigated = run_readonly_investigators(
            conn, budget, handoff, principal_id=claim["principal_id"]
        )
    except Exception as exc:  # a rejected tool, not a crash drill
        trace.add("error", {"reason": "investigator_failed", "exception": type(exc).__name__})
        return done("failed", 0, "investigator_failed")

    tools = investigated["tools"]
    order_view = tools.get("lookup_order") or {}

    # Order missing or outside this principal's scope: escalate, and let nothing
    # about the order into the trace or the reply (T05).
    if not order_view.get("visible"):
        trace.add("investigator", {"lookup_order": {"visible": False, "reason": order_view.get("reason")}})
        complete(budget, seed=seed, purpose="draft", prompt=f"escalated:{claim_id}")
        return done("escalated", 0, order_view.get("reason"))

    order = order_view["order"]
    history = tools.get("lookup_refund_history") or {}
    trace.add(
        "investigator",
        {
            "order_status": order["status"],
            "delay_days": order["delay_days"],
            "damage_verified": order["damage_verified"],
            "shipping_fee_vnd": order["shipping_fee_vnd"],
            "refund_count": history.get("refund_count"),
            "refunded_vnd": history.get("refunded_vnd"),
        },
    )

    # Money came from compute_compensation inside the investigator run, off the
    # order row and the current policy. No model picked it.
    quote = tools.get("compute_compensation")
    if not quote:
        trace.add("error", {"reason": "missing_quote"})
        return done("failed", 0, "missing_quote")

    proposal = int(quote["amount_vnd"])
    trace.add(
        "quote",
        {
            "amount_vnd": proposal,
            "reason": quote.get("reason"),
            "clause_ids": quote.get("clause_ids"),
            "parts": quote.get("parts"),
        },
    )
    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

    # Nothing owed: the orchestrator decides this itself, so the host is not
    # called and no policy_denied audit is written (T02, T06, T09).
    if proposal <= 0:
        trace.add("decision", {"status": "denied", "reason": quote.get("reason")})
        return done("denied", 0, quote.get("reason"))

    # Only the orchestrator calls the host, and it passes the FULL quote. The
    # host subtracts what earlier claims took for this order (T13, T14).
    try:
        host = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        # Flush the trace, then let the crash propagate: one refund is kept by
        # the ledger transaction and the idempotency key, not by an except (T12).
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    trace.add("host", {"ok": bool(host["ok"]), "reason": host["reason"]})
    if not host["ok"]:
        return done("failed" if host["conflict"] else "denied", proposal, host["reason"])

    return done("resolved", proposal, None)
