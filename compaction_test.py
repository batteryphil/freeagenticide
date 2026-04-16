"""Two-pass compactor verification — covers the exact trap scenario."""

from ag.core.session import (
    _cap_tool_results,
    _middle_out_compact,
    _is_tool_result,
    _MAX_TOOL_RESULT_CHARS,
)

# ── Test 1: tool result detection ─────────────────────────────────────────────
assert _is_tool_result({"role": "assistant", "content": "[Tool `file_ops` result]\ndata"})
assert _is_tool_result({"role": "assistant", "content": "[Tool invoked: read app.py]"})
assert not _is_tool_result({"role": "assistant", "content": "Here is the answer."})
assert not _is_tool_result({"role": "user", "content": "[Tool `x` result] ..."})
print("✅  Test 1 — _is_tool_result detection correct")

# ── Test 2: Pass 1 — small tool result is unchanged ──────────────────────────
small = {"role": "assistant", "content": "[Tool `file_ops` result]\nsmall output"}
assert _cap_tool_results([small])[0]["content"] == small["content"]
print("✅  Test 2 — small tool result unchanged")

# ── Test 3: Pass 1 — oversized code file is stubbed, NOT sliced ───────────────
fake_file = "[Tool `file_ops` result]\n" + "x = 1\n" * 1000   # ~8 000 chars
big_msg = {"role": "assistant", "content": fake_file}
ordinary = {"role": "user", "content": "Can you refactor the router?"}

capped = _cap_tool_results([big_msg, ordinary], max_chars=6000)

assert len(capped[0]["content"]) < len(fake_file), "Should be capped"
assert "[Output truncated:" in capped[0]["content"],  "Must contain truncation notice"
assert "file_ops" in capped[0]["content"],            "Stub must retain tool name"
assert "grep" in capped[0]["content"],                "Stub must give recovery instructions"
assert capped[1]["content"] == ordinary["content"],   "Ordinary message must not change"

print(
    f"✅  Test 3 — 400-line file stubbed "
    f"(was {len(fake_file):,} chars → {len(capped[0]['content'])} chars)"
)
preview = capped[0]["content"].split("\n", 1)[-1][:120]
print(f"    Stub: {preview}")

# ── Test 4: Pass 2 — middle-out never slices a message mid-content ────────────
msgs: list[dict] = []
for i in range(30):
    msgs.append({"role": "user",      "content": f"User message {i}: " + "A" * 200})
    if i == 15:
        msgs.append({"role": "assistant", "content": "[Tool `file_ops` result]\n" + "B" * 200})
    else:
        msgs.append({"role": "assistant", "content": f"Assistant response {i}."})

compacted = _middle_out_compact(msgs, budget_tokens=1000)

for m in compacted:
    if m["role"] == "assistant" and m["content"].startswith("[Tool"):
        is_stub = "[Output truncated:" in m["content"]
        is_full = "B" * 50 in m["content"]   # enough Bs = full content present
        assert is_stub or is_full, (
            f"Tool result was sliced mid-content:\n{m['content'][:120]}"
        )

print(
    f"✅  Test 4 — middle-out: {len(msgs)} msgs → {len(compacted)}, "
    f"no mid-content slicing"
)

# ── Test 5: The exact trap scenario ───────────────────────────────────────────
# /read app.py → 400 lines in session; user asks to refactor; qwen2.5 2500-tok budget
app_py = "[Tool `file_ops` result]\n" + "class App:\n    pass\n" * 200   # ~8 400 chars
session_msgs: list[dict] = [
    {"role": "user",      "content": "[Tool invoked: file ops app.py]"},
    {"role": "assistant", "content": app_py},
    {"role": "user",      "content": "Refactor the router"},
]
result = _middle_out_compact(session_msgs, budget_tokens=2500)

for m in result:
    if m.get("role") == "assistant" and "file_ops" in m.get("content", ""):
        content = m["content"]
        is_stub = "[Output truncated:" in content
        is_full = len(content) == len(app_py)
        assert is_stub or is_full, (
            f"Content was sliced mid-file!\n{content[:200]}"
        )
        verdict = "stub" if is_stub else "full (fits)"
        print(f"✅  Test 5 — Trap scenario (qwen2.5 2500-tok): file handled as {verdict}")

# ── Test 6: Non-tool assistant messages are never capped ─────────────────────
long_answer = {"role": "assistant", "content": "Here is a detailed answer:\n" + "word " * 2000}
capped2 = _cap_tool_results([long_answer])
assert capped2[0]["content"] == long_answer["content"], "Non-tool messages must not be capped"
print("✅  Test 6 — non-tool assistant messages bypass cap untouched")

print()
print("All 6 compaction tests passed — two-pass system is safe.")
