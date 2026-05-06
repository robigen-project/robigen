"""
Lightweight per-iteration timing + token/cost metrics tracker.

Used to measure execution time and API cost for the paper's
"Execution Time" subsection. Module-level singleton state — the test loop
is serial, so no locking needed.

Usage from test_main.py:
    from utils import metrics
    metrics.start_iteration(iter_dir)
    with metrics.step("target_baseline"):
        target_agent.run_task(...)
    ...
    metrics.end_iteration()

Usage from agent clients:
    from utils import metrics
    metrics.record_call(model_id, input_tokens=42, output_tokens=17)
"""

import json
import os
import time
from contextlib import contextmanager


# Pricing in USD. Verify against current OpenAI + Google rates before the paper run.
# Rates as of 2025-Q2. Update per-model entries here, not inline elsewhere.
PRICING = {
    # OpenAI
    "gpt-4o":                {"input_per_1m": 2.50, "output_per_1m": 10.00},
    # Google Gemini
    "gemini-2.5-flash":      {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "models/gemini-2.5-flash": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "gemini-flash-latest":   {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "models/gemini-flash-latest": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "gemini-robotics-er-1.5-preview": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    "models/gemini-robotics-er-1.5-preview": {"input_per_1m": 0.30, "output_per_1m": 2.50},
    # Image generation — flat per-image
    "nano-banana-pro-preview": {"per_image": 0.039},
    "models/nano-banana-pro-preview": {"per_image": 0.039},
    "gemini-3-pro-image-preview": {"per_image": 0.039},
    "models/gemini-3-pro-image-preview": {"per_image": 0.039},
}


_state = {
    "iter_dir": None,
    "iter_t0": None,
    "steps": [],          # list of {name, elapsed_s, calls, step_cost_usd}
    "current_step": None, # dict being filled in
}


def _cost_for_call(model_id: str, input_tokens, output_tokens, is_image: bool) -> float:
    price = PRICING.get(model_id)
    if price is None:
        return 0.0
    if is_image:
        return float(price.get("per_image", 0.0))
    in_cost = (input_tokens or 0) / 1_000_000 * price.get("input_per_1m", 0.0)
    out_cost = (output_tokens or 0) / 1_000_000 * price.get("output_per_1m", 0.0)
    return in_cost + out_cost


def start_iteration(iter_dir: str) -> None:
    _state["iter_dir"] = iter_dir
    _state["iter_t0"] = time.perf_counter()
    _state["steps"] = []
    _state["current_step"] = None


@contextmanager
def step(name: str):
    if _state["iter_dir"] is None:
        # Not inside an instrumented iteration — no-op.
        yield
        return
    step_record = {
        "name": name,
        "elapsed_s": 0.0,
        "calls": [],
        "step_cost_usd": 0.0,
    }
    _state["current_step"] = step_record
    t0 = time.perf_counter()
    try:
        yield
    finally:
        step_record["elapsed_s"] = time.perf_counter() - t0
        _state["steps"].append(step_record)
        _state["current_step"] = None


def record_call(model_id: str, input_tokens=None, output_tokens=None, is_image: bool = False) -> None:
    if _state["iter_dir"] is None or _state["current_step"] is None:
        return
    cost = _cost_for_call(model_id, input_tokens, output_tokens, is_image)
    call_entry = {
        "model": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "is_image": is_image,
        "cost_usd": cost,
    }
    _state["current_step"]["calls"].append(call_entry)
    _state["current_step"]["step_cost_usd"] += cost


def end_iteration() -> dict:
    if _state["iter_dir"] is None:
        return {}
    steps = _state["steps"]
    compute_time = sum(s["elapsed_s"] for s in steps)
    total_cost = sum(s["step_cost_usd"] for s in steps)
    total_calls = sum(len(s["calls"]) for s in steps)
    wall_clock = time.perf_counter() - _state["iter_t0"]
    data = {
        "steps": steps,
        "totals": {
            "compute_time_s": compute_time,
            "wall_clock_s": wall_clock,
            "cost_usd": total_cost,
            "api_calls": total_calls,
        },
    }
    out_path = os.path.join(_state["iter_dir"], "metrics.json")
    try:
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[metrics] failed to write {out_path}: {e}")
    _state["iter_dir"] = None
    _state["iter_t0"] = None
    _state["steps"] = []
    _state["current_step"] = None
    return data
