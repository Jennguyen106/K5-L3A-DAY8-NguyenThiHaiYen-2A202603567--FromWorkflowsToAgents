"""Shape A — deterministic workflow. Student work.

Signature (do not change):

    run_claim(claim_id, *, seed, store_path, crash_at=None) -> RunResult

Suggested steps. Money stays in code (`lab8.tools.compute_compensation`).

1. Open the store. Read the claim through `get_claim_view` (not SELECT *).
2. Missing order_id -> status `needs_info`. Do not write the ledger.
3. `lookup_order`. If not visible -> `escalated`. Do not copy phone, address, item, internal note.
4. Quote from the order row. Ignore delay numbers written in the ticket.
5. Quote amount 0 -> `denied`. Do not call issue_refund.
6. Quote amount > 0 -> `durability.issue_refund(conn, claim_id, <full quote>)`.
   Pass the FULL quote. The host checks the claim's own approval and subtracts
   what earlier claims already got for the same order (T13, T14). Do not
   subtract it yourself or the host subtracts twice.
   Auth failure or order already refunded -> `denied` (the host writes `policy_denied`).
   `proposal_amount` stays the full quote. Amount conflict -> `failed`.
7. Success -> `resolved`. One ledger row, one `refund_committed` audit.
8. Use MockLLM only to draft the reply text, if you want a model call at all.

The model must not choose the refund amount and must not commit the refund.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.mock_llm import complete
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import compute_compensation, get_claim_view, lookup_order, tool_cost
from lab8.trace import Trace

SHAPE = "workflow"


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

    # Step 1 — the allowlisted claim view. The raw claim row carries
    # parent_secret and raw_headers; neither may reach a trace.
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim.get("found"):
        trace.add("error", {"reason": "unknown_claim"})
        return done("failed", 0, "unknown_claim")

    # Step 2 — no order id on the claim. The ticket may name one; it is user
    # text, so it is not used (T04).
    if not claim.get("order_id"):
        complete(budget, seed=seed, purpose="draft", prompt=f"needs_info:{claim_id}")
        trace.add("decision", {"status": "needs_info", "reason": "missing_order_id"})
        return done("needs_info", 0, "missing_order_id")

    # Step 3 — the order, scoped to this claim's principal.
    budget.add_tool(tool_cost())
    order_view = lookup_order(conn, claim["order_id"], claim["principal_id"])
    if not order_view.get("visible"):
        trace.add("observe", {"tool": "lookup_order", "visible": False, "reason": order_view.get("reason")})
        complete(budget, seed=seed, purpose="draft", prompt=f"escalated:{claim_id}")
        return done("escalated", 0, order_view.get("reason"))

    # Only allowlisted order fields are logged — no phone, address, item name or
    # internal note (T05, T10).
    order = order_view["order"]
    trace.add(
        "observe",
        {
            "tool": "lookup_order",
            "visible": True,
            "order_status": order["status"],
            "delay_days": order["delay_days"],
            "damage_verified": order["damage_verified"],
            "shipping_fee_vnd": order["shipping_fee_vnd"],
        },
    )

    # Step 4 — money from the order row and the current policy. The ticket's own
    # delay figure and any clause it cites are ignored (T02, T06, T09).
    budget.add_tool(tool_cost())
    quote = compute_compensation(conn, order)
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

    # Step 5 — nothing is owed. This is the workflow's own decision, so the host
    # is not called and no policy_denied audit is written (T02, T06, T09).
    if proposal <= 0:
        trace.add("decision", {"status": "denied", "reason": quote.get("reason")})
        return done("denied", 0, quote.get("reason"))

    # Step 6 — the FULL quote goes to the host. The host checks this claim's own
    # approval and subtracts what earlier claims took for the same order (T13,
    # T14). Subtracting here would make the host subtract twice.
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
        # A different amount on a claim that already paid is a conflict, not a
        # policy denial. proposal_amount stays the full quote either way.
        return done("failed" if host["conflict"] else "denied", proposal, host["reason"])

    # Step 7 — one ledger row, one refund_committed audit.
    return done("resolved", proposal, None)
