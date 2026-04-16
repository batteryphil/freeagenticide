"""Smoke test for the 9-step agent spawn system."""

# ── Step 1-2: AgentChunk + AgentContext ──────────────────────────────────────
from ag.core.context import AgentChunk, AgentContext
chunk = AgentChunk(text="hello", agent_name="developer", depth=1)
assert chunk.depth == 1
print("[1-2] ✅ AgentChunk + AgentContext import OK")

# ── Step 3: Session.last_n ───────────────────────────────────────────────────
from ag.core.session import Session
s = Session()
s.add_user("msg1"); s.add_user("msg2"); s.add_user("msg3")
last = s.last_n(2)
assert len(last) == 2 and last[-1].content == "msg3"
s2 = Session(seed_messages=last)
assert s2.message_count == 2
print("[3]   ✅ Session.last_n + seed_messages OK")

# ── Step 4-5: AgentProfile + load_profile + profiles on disk ─────────────────
from ag.core.spawn import load_profile, list_profiles, AgentProfile
dev = load_profile("developer")
assert dev.name == "developer", f"name mismatch: {dev.name}"
assert "Developer" in dev.title, f"title missing: {dev.title}"
assert len(dev.system_prompt) > 0, "developer is missing system_prompt"
all_p = list_profiles()
names = [p.name for p in all_p]
assert "developer" in names, f"developer not in {names}"
assert "researcher" in names
assert "coder" in names
print(f"[4-5] ✅ Profiles: {names}")

# ── Step 6: Router.decide complexity_hint ───────────────────────────────────
from ag.core.config import load_config
from ag.core.router import Router
from ag.providers.registry import ProviderRegistry
cfg = load_config()
registry = ProviderRegistry(cfg.providers)
router = Router(cfg.routing, registry)
d1 = router.decide("hi", complexity_hint=0.0)
d2 = router.decide("hi", complexity_hint=1.0)
assert d1.complexity_score == 0.0, f"hint=0 gave score {d1.complexity_score}"
assert d2.complexity_score == 1.0, f"hint=1 gave score {d2.complexity_score}"
print(f"[6]   ✅ complexity_hint: 0→{d1.reason}, 1→{d2.reason}")

# ── Step 7: Agent class + _extract_tool_call ─────────────────────────────────
from ag.core.agent import Agent, _extract_tool_call

raw = (
    'Thinking...\n```json\n'
    '{"tool_name": "call_subordinate", "tool_args": '
    '{"message": "do it", "agent_profile": "developer"}}\n```'
)
tc = _extract_tool_call(raw)
assert tc is not None, "tool call not extracted"
assert tc["tool_name"] == "call_subordinate"
assert tc["tool_args"]["agent_profile"] == "developer"
print("[7]   ✅ _extract_tool_call works")

profile = load_profile("developer")
assert profile.name == "developer"
print(f"[7]   ✅ AgentProfile.name = {profile.name}, temp = {profile.temperature}")

# ── Step 8: call_subordinate tool schema ────────────────────────────────────
from ag.tools.call_subordinate import CallSubordinateTool
tool = CallSubordinateTool()
schema = tool.describe()
assert schema["name"] == "call_subordinate"
assert "agent_profile" in schema["parameters"]["properties"]
assert "reset" in schema["parameters"]["properties"]
print("[8]   ✅ CallSubordinateTool schema OK")

# ── Step 9: depth-aware ChatPanel ────────────────────────────────────────────
from ag.tui.chat_panel import ChatPanel, ChatMessage, _depth_colour
assert _depth_colour(0) == "#1a6b3c", f"root colour wrong: {_depth_colour(0)}"
assert _depth_colour(1) == "#1a4a6b", f"depth-1 colour wrong: {_depth_colour(1)}"
assert _depth_colour(99) == "#7a4a2e", f"capped colour wrong: {_depth_colour(99)}"
print("[9]   ✅ depth_colour map OK")

# ── App wiring ────────────────────────────────────────────────────────────────
from ag.tui.app import AntigravityApp
app = AntigravityApp(cfg)
assert hasattr(app, "_agent_context"), "_agent_context missing"
assert hasattr(app, "_active_chunks"), "_active_chunks missing"
assert hasattr(app, "_run_agent"), "_run_agent missing"
assert isinstance(app._agent_context, AgentContext)
print("[app] ✅ AntigravityApp _agent_context + _run_agent wired")

print()
print("All 9 steps verified. Spawn system ready.")
