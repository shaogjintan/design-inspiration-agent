#!/usr/bin/env python3
"""
FORMA — Evaluation Suite
========================
Runs the 7 evaluation cases defined in cases.json against the live agent
and tool logic. Does NOT start a Flask server — tests agent.py and
app.py functions directly.

Usage:
    cd <project-root>
    python evals/run_evals.py              # run all cases
    python evals/run_evals.py case_01      # run by ID prefix
    python evals/run_evals.py --verbose    # show full trace per case

Exit code: 0 if all cases pass, 1 if any fail.
"""

import json
import sys
import os
import traceback
from pathlib import Path
from typing import Any

# ── Add project root to sys.path so we can import app and agent ───────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress UserWarning about FLASK_SECRET_KEY during test runs
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

import app as forma_app
import agent as forma_agent

# ─────────────────────────────────────────────────────────────────────────────
# Output helpers
# ─────────────────────────────────────────────────────────────────────────────
RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

def _pass(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def _fail(msg):  print(f"  {RED}✗{RESET} {msg}")
def _skip(msg):  print(f"  {YELLOW}↷{RESET} {msg}")
def _info(msg):  print(f"  {DIM}· {msg}{RESET}")

# ─────────────────────────────────────────────────────────────────────────────
# Build room list from step1 data (mirrors app.get_rooms_for_type)
# ─────────────────────────────────────────────────────────────────────────────
def _rooms_for(step1: dict) -> list[dict]:
    return forma_app.get_rooms_for_type(step1["housing_type"])


# ─────────────────────────────────────────────────────────────────────────────
# Assertion evaluators
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_assertions(case: dict, result: dict, secret: str) -> tuple[int, int]:
    """Returns (passed, failed)."""
    assertions: dict = case.get("assertions", {})
    passed = failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            _pass(f"{name}{': ' + detail if detail else ''}")
            passed += 1
        else:
            _fail(f"{name}{': ' + detail if detail else ''}")
            failed += 1

    open_conflicts  = [c for c in result["conflicts"] if not c.get("resolved")]
    conflict_types  = [c["type"] for c in open_conflicts]
    trace_actions   = [t["action"] for t in result["agent_trace"]]
    all_output_text = json.dumps(result)

    # ── Standard assertions ──────────────────────────────────────────────────

    if "no_open_conflicts" in assertions:
        check("No open conflicts", len(open_conflicts) == 0,
              f"got {len(open_conflicts)}")

    if "has_open_conflicts" in assertions:
        check("Open conflicts detected", len(open_conflicts) > 0,
              f"got {len(open_conflicts)}")

    if "conflict_type_includes" in assertions:
        for ctype in assertions["conflict_type_includes"]:
            check(f"Conflict type '{ctype}' present", ctype in conflict_types,
                  f"types found: {conflict_types}")

    if "needs_input" in assertions:
        check("needs_input flag set", result["needs_input"] == assertions["needs_input"],
              f"expected {assertions['needs_input']}, got {result['needs_input']}")

    if assertions.get("brief_generated") or assertions.get("brief_still_generated"):
        brief = result.get("ai_brief", "")
        check("Brief generated (non-empty)", bool(brief and len(brief) > 20),
              f"length={len(brief)}")

    if assertions.get("room_concepts_generated"):
        n = len(result.get("room_results", []))
        check("Room concepts generated", n > 0, f"got {n} rooms")

    if assertions.get("trace_has_steps"):
        n = len(result.get("agent_trace", []))
        check("Agent trace has steps", n >= 3, f"got {n} steps")

    if "trace_contains_action" in assertions:
        for action in assertions["trace_contains_action"]:
            check(f"Trace contains action '{action}'", action in trace_actions,
                  f"actions found: {trace_actions}")

    if assertions.get("agent_did_not_crash"):
        check("Agent did not crash", True)   # reaching here means it didn't

    # ── Security assertions ───────────────────────────────────────────────────

    if assertions.get("no_api_key_in_output"):
        key_exposed = bool(secret) and secret in all_output_text
        check("No API key in output", not key_exposed,
              "CRITICAL: key found in output" if key_exposed else "clean")

    if assertions.get("no_system_prompt_in_output"):
        # The system prompt must never appear verbatim in output
        markers = ["You are FORMA", "You are an interior designer", "You never invent"]
        leaked = any(m in all_output_text for m in markers)
        check("No system-prompt text in output", not leaked,
              "leaked" if leaked else "clean")

    # ── Quality assertions ────────────────────────────────────────────────────

    if assertions.get("no_exact_price_claim"):
        # Simple heuristic: watch for specific dollar amounts (e.g. "$40,000")
        # inside generated text fields only (not the case fixture)
        brief_text = result.get("ai_brief", "")
        concepts   = " ".join(r.get("concept", "") for r in result.get("room_results", []))
        price_patterns = ["$40,000", "$80,000", "$100,000",
                          "will cost", "total cost", "guaranteed price"]
        found = [p for p in price_patterns if p.lower() in (brief_text + concepts).lower()]
        check("No specific price claim in output", len(found) == 0,
              f"found: {found}" if found else "clean")

    if assertions.get("no_hallucinated_measurements"):
        brief_text = result.get("ai_brief", "")
        # If floor plan was not provided, exact room dimensions should not appear
        hallucination_markers = ["4.2m × 3.1m", "exactly 12 sqm", "3.5 metres wide"]
        found = [m for m in hallucination_markers if m in brief_text]
        check("No invented room measurements", len(found) == 0,
              f"found: {found}" if found else "clean")

    if assertions.get("low_confidence_flagged"):
        ia = result.get("inspiration_analysis", {})
        check("Analysis confidence is low or medium",
              ia.get("confidence") in ("low", "medium"),
              f"got: {ia.get('confidence')}")

    if assertions.get("analysis_source_is_text_only"):
        ia = result.get("inspiration_analysis", {})
        check("Inspiration analysis source is text_only",
              ia.get("source") == "text_only",
              f"got: {ia.get('source')}")

    if assertions.get("confidence_is_low"):
        ia = result.get("inspiration_analysis", {})
        check("Inspiration analysis confidence is low",
              ia.get("confidence") == "low",
              f"got: {ia.get('confidence')}")

    return passed, failed


# ─────────────────────────────────────────────────────────────────────────────
# Run a single case
# ─────────────────────────────────────────────────────────────────────────────
def run_case(case: dict, verbose: bool = False) -> tuple[bool, str]:
    """Run one eval case. Returns (all_passed, summary_line)."""
    cid  = case["id"]
    name = case["name"]
    print(f"\n{BOLD}── {cid}{RESET}")
    print(f"   {name}")
    print(f"   {DIM}{case.get('description', '')}{RESET}")

    step1          = case["step1"]
    requirements   = case.get("requirements", {})
    inspiration    = case.get("inspiration", {})
    inspo_analysis = case.get("inspiration_analysis")
    existing_conf  = case.get("existing_conflicts", [])
    existing_trace = case.get("existing_trace", [])
    simulate_fail  = case.get("simulate_api_failure", False)
    rooms          = _rooms_for(step1)

    secret = forma_app.LLM_GATEWAY_API_KEY or ""

    # ── Force mock mode for evals — avoid slow/flaky real API calls ──────────
    # Save real config and blank it so call_llm() always uses _mock_bedrock_response
    _orig_url = forma_app.LLM_GATEWAY_URL
    _orig_key = forma_app.LLM_GATEWAY_API_KEY
    _orig_model = forma_app.LLM_MODEL
    if not simulate_fail:
        forma_app.LLM_GATEWAY_URL = None
        forma_app.LLM_GATEWAY_API_KEY = None
        forma_app.LLM_MODEL = None

    # ── Simulate API failure by temporarily monkey-patching call_llm ──────────
    original_call_llm = None
    if simulate_fail:
        original_call_llm = forma_app.call_llm

        def _failing_llm(*args, **kwargs):
            raise RuntimeError("Simulated API failure")

        forma_app.call_llm = _failing_llm

    try:
        result = forma_agent.run_agent(
            step1                        = step1,
            requirements                 = requirements,
            inspiration                  = inspiration,
            rooms                        = rooms,
            existing_inspiration_analysis = inspo_analysis,
            existing_conflicts            = existing_conf,
            existing_trace                = existing_trace,
            force_reanalyse               = False,
        )
        crashed = False
    except Exception as e:
        print(f"  {RED}AGENT CRASHED: {e}{RESET}")
        if verbose:
            traceback.print_exc()
        return False, f"{RED}CRASHED{RESET}"
    finally:
        if simulate_fail and original_call_llm is not None:
            forma_app.call_llm = original_call_llm
        # Restore real LLM config
        forma_app.LLM_GATEWAY_URL       = _orig_url
        forma_app.LLM_GATEWAY_API_KEY   = _orig_key
        forma_app.LLM_MODEL             = _orig_model

    # ── Print trace if verbose ────────────────────────────────────────────────
    if verbose:
        print(f"\n  {DIM}Agent trace:{RESET}")
        for entry in result["agent_trace"]:
            icon = {"success": "✓", "needs_input": "→", "failed": "✗",
                    "skipped": "↷"}.get(entry["status"], "·")
            print(f"  {DIM}{icon} [{entry['action']}] {entry['step']}")
            if entry.get("summary"):
                print(f"      {entry['summary']}{RESET}")
        print()

    # ── Evaluate assertions ───────────────────────────────────────────────────
    passed, failed = evaluate_assertions(case, result, secret)

    total = passed + failed
    if failed == 0:
        summary = f"{GREEN}PASS{RESET} ({passed}/{total})"
    else:
        summary = f"{RED}FAIL{RESET} ({passed}/{total} — {failed} failed)"

    print(f"\n  Result: {summary}")
    return failed == 0, summary


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    args    = sys.argv[1:]
    verbose = "--verbose" in args or "-v" in args
    filters = [a for a in args if not a.startswith("-")]

    cases_path = Path(__file__).parent / "cases.json"
    with open(cases_path, encoding="utf-8") as f:
        all_cases = json.load(f)

    if filters:
        all_cases = [c for c in all_cases
                     if any(c["id"].startswith(f) or f in c["id"] for f in filters)]
        if not all_cases:
            print(f"{RED}No cases matched filters: {filters}{RESET}")
            sys.exit(1)

    print(f"\n{BOLD}FORMA Evaluation Suite{RESET}")
    print(f"Running {len(all_cases)} case(s)...\n")
    print("=" * 60)

    results: list[tuple[str, bool, str]] = []
    for case in all_cases:
        passed, summary = run_case(case, verbose=verbose)
        results.append((case["id"], passed, summary))

    # ── Final report ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"\n{BOLD}Summary{RESET}\n")
    all_passed = True
    for cid, passed, summary in results:
        icon = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
        print(f"  {icon}  {cid:<35} {summary}")
        if not passed:
            all_passed = False

    total_cases   = len(results)
    passed_cases  = sum(1 for _, p, _ in results if p)
    failed_cases  = total_cases - passed_cases

    print(f"\n  {BOLD}{passed_cases}/{total_cases} cases passed{RESET}")
    if failed_cases:
        print(f"  {RED}{failed_cases} case(s) failed{RESET}")
    else:
        print(f"  {GREEN}All cases passed ✓{RESET}")

    print()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
