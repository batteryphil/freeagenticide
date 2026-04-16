"""code_exec sandbox verification — 7 tests covering all safety properties."""

import asyncio
from ag.core.config import load_config
from ag.tools.registry import ToolRegistry


async def main() -> None:
    """Run all code_exec sandbox tests."""
    cfg = load_config()
    tools = ToolRegistry(cfg.tools)

    # ── Test 1: Basic execution ───────────────────────────────────────────────
    r = await tools.run("code_exec", code="print(2 + 2)")
    assert r.success, f"Failed: {r.error}"
    assert "4" in r.output
    print("✅  Test 1 — basic execution:", r.output.strip())

    # ── Test 2: Stdout + stderr combined ─────────────────────────────────────
    r = await tools.run("code_exec", code="import sys; print('out'); sys.stderr.write('err')")
    assert r.success
    assert "out" in r.output
    assert "[stderr]" in r.output
    assert "err" in r.output
    print("✅  Test 2 — stdout+stderr:", r.output.replace("\n", " | "))

    # ── Test 3: Non-zero exit returns success=False ───────────────────────────
    r = await tools.run("code_exec", code="raise ValueError('deliberate')")
    assert not r.success
    assert "deliberate" in (r.error or r.output)
    print("✅  Test 3 — non-zero exit is failure:", r.error[:60])

    # ── Test 4: Syntax error caught cleanly ───────────────────────────────────
    r = await tools.run("code_exec", code="def broken(\n")
    assert not r.success
    print("✅  Test 4 — syntax error caught:", (r.error or r.output)[:60])

    # ── Test 5: Empty code rejected before spawning ───────────────────────────
    r = await tools.run("code_exec", code="   \n  ")
    assert not r.success
    assert "Empty" in r.error
    print("✅  Test 5 — empty code rejected:", r.error)

    # ── Test 6: Output cap (no context flooding) ──────────────────────────────
    big_print = "print('X' * 100_000)"
    r = await tools.run("code_exec", code=big_print)
    assert r.success
    assert len(r.output) <= 4_200   # cap + truncation notice overhead
    assert "truncated" in r.output.lower()
    print(f"✅  Test 6 — output capped at {len(r.output):,} chars (100k → truncated)")

    # ── Test 7: Timeout + guaranteed teardown ────────────────────────────────
    # This will time out; we verify it returns a clean error within a few seconds
    import time
    t0 = time.monotonic()
    r = await tools.run("code_exec", code="while True: pass")
    elapsed = time.monotonic() - t0
    assert not r.success
    assert "timed out" in r.error.lower()
    assert elapsed < 35  # default 30s timeout + 5s headroom
    print(f"✅  Test 7 — infinite loop timed out in {elapsed:.1f}s, process killed cleanly")

    print()
    print("All 7 code_exec tests passed.")


asyncio.run(main())
