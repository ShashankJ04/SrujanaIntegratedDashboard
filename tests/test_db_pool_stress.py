"""
Stress test for backend.db connection pooling.
Run from project root: python tests/test_db_pool_stress.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.app import create_app
from backend.db import _get_erp_pool, fetch_all, fetch_one


def _pool_snapshot():
    pool = _get_erp_pool()
    return {
        "max_total": pool._max_total,
        "max_idle": pool._max_size,
        "created": pool._created,
        "idle_in_queue": pool._pool.qsize(),
    }


def _worker_burst(worker_id: int, queries_per_worker: int) -> dict:
    app = _worker_burst.app  # type: ignore[attr-defined]
    errors = []
    t0 = time.perf_counter()
    try:
        with app.app_context():
            for i in range(queries_per_worker):
                row = fetch_one("SELECT %s AS wid, %s AS q", (worker_id, i))
                if row is None or row.get("wid") != worker_id:
                    errors.append(f"bad row {row}")
            fetch_all("SELECT 1 AS ok LIMIT 1")
    except Exception as exc:
        errors.append(repr(exc))
    elapsed = time.perf_counter() - t0
    return {"worker_id": worker_id, "errors": errors, "elapsed": elapsed}


def _simulate_hub_request() -> dict:
    """One logical page load: several sequential queries (like production calendar)."""
    app = _simulate_hub_request.app  # type: ignore[attr-defined]
    errors = []
    try:
        with app.app_context():
            fetch_one("SELECT 1 AS step1")
            fetch_one("SELECT 2 AS step2")
            fetch_all("SELECT 3 AS step3 LIMIT 1")
            fetch_one("SELECT 4 AS step4")
            fetch_all("SELECT 5 AS step5 LIMIT 1")
    except Exception as exc:
        errors.append(repr(exc))
    return {"errors": errors}


def _run_case(name: str, submit_fn, workers: int, rounds: int = 1) -> bool:
    print(f"\n=== {name} ===")
    before = _pool_snapshot()
    print(f"  before: {before}")

    errors: list = []
    t0 = time.perf_counter()
    task_count = workers * rounds
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(submit_fn, n) for n in range(task_count)]
        for f in as_completed(futures):
            try:
                result = f.result()
                if result.get("errors"):
                    errors.extend(result["errors"])
            except Exception as exc:
                errors.append(repr(exc))

    elapsed = time.perf_counter() - t0
    time.sleep(0.2)
    after = _pool_snapshot()
    print(f"  after:  {after}")
    print(f"  time:   {elapsed:.2f}s  tasks: {task_count}  errors: {len(errors)}")
    if errors:
        print(f"  first error: {errors[0]}")
        return False

    leaked = after["created"] > after["max_total"]
    not_returned = after["created"] > after["idle_in_queue"] + 2
    if leaked:
        print("  FAIL: created exceeds max_total (leak or accounting bug)")
        return False
    if after["created"] > before["max_idle"] + 5 and after["idle_in_queue"] == 0:
        print("  WARN: many connections still checked out after work finished")

    ok = after["created"] <= after["max_total"] and len(errors) == 0
    print("  PASS" if ok else "  FAIL")
    return ok


def main() -> int:
    app = create_app()
    _worker_burst.app = app
    _simulate_hub_request.app = app

    with app.app_context():
        snap = _pool_snapshot()
        print("Pool config:", snap)
        try:
            fetch_one("SELECT 1 AS ping")
        except Exception as exc:
            print(f"Cannot connect to database: {exc}")
            print("Stress test skipped — fix DB credentials in .env / config.py")
            return 1

    results = []
    results.append(
        _run_case("50 workers x 8 queries", lambda n: _worker_burst(n, 8), workers=50, rounds=1)
    )

    results.append(
        _run_case("40 parallel hub-style requests", lambda n: _simulate_hub_request(), workers=40, rounds=1)
    )

    results.append(
        _run_case("30 workers x 20 queries", lambda n: _worker_burst(n, 20), workers=30, rounds=1)
    )

    # Burst above max_total (30) — should use overflow, then recover
    results.append(
        _run_case("35 workers x 5 queries (overflow)", lambda n: _worker_burst(n, 5), workers=35, rounds=1)
    )

    with app.app_context():
        final = _pool_snapshot()
        print(f"\n=== Final pool state ===\n  {final}")
        if final["created"] <= final["max_idle"]:
            print("  Connections returned to pool (created <= idle cap) — reuse OK")
        elif final["idle_in_queue"] > 0:
            print(f"  {final['idle_in_queue']} idle connection(s) in queue — reuse OK")
        else:
            print("  CHECK: elevated created count after stress")

    passed = all(results)
    print("\n" + ("ALL STRESS TESTS PASSED" if passed else "SOME TESTS FAILED"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
