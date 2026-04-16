# Credits

Freeagenticide is built on the shoulders of several excellent open-source projects.
Thank you to everyone whose work made this possible.

---

## Core Agent Architecture

### [agent-zero](https://github.com/frdel/agent-zero) — Jan Mrázek (frdel)
**License:** MIT

The recursive multi-agent architecture in this project is substantially derived from agent-zero.
Specifically, the following patterns are borrowed directly or adapted from that codebase:

- **`call_subordinate` tool** — the naming, schema, and delegation mechanism
- **Agent profile / YAML profile system** — `agent.yaml` + `prompts/` shard loading,
  `load_profile()`, `_merge_profiles()`, and the `agents/` directory layout
- **ReAct-style JSON tool loop** — the ```json `{"tool_name": ..., "tool_args": ...}` ```
  fenced-block format, `_extract_tool_call()` regex, and the `message_loop` iteration pattern
- **Sub-agent spawning** — `Agent._call_subordinate()`, depth tracking, `max_depth` guard,
  shared `AgentContext` reference across the agent tree
- **`call_subordinate` tool schema** — the `message`, `agent_profile`, `reset`, `context_msgs`
  parameter names and descriptions

The session compaction (`MiddleOut` + tool result capping),
the provider registry/router abstraction, and the UI-bridged tools
(`write_to_editor`, `run_in_ui`, code-block auto-run interception) are original to this project.

---

## UI & Frontend

### [Monaco Editor](https://github.com/microsoft/monaco-editor) — Microsoft
**License:** MIT

The code editor component. Wrapped via
[`@monaco-editor/react`](https://github.com/suren-atoyan/monaco-react) by Suren Atoyan (MIT).

### [React](https://github.com/facebook/react) — Meta Platforms
**License:** MIT

Core UI framework (`react` v19, `react-dom`, `react-markdown`).

### [Vite](https://github.com/vitejs/vite) — Evan You & contributors
**License:** MIT

Build tool and dev server.

### [remark-gfm](https://github.com/remarkjs/remark-gfm) — unified collective
**License:** MIT

GitHub Flavored Markdown support in chat message rendering.

---

## Backend

### [FastAPI](https://github.com/tiangolo/fastapi) — Sebastián Ramírez
**License:** MIT

The async HTTP and WebSocket server framework.

### [uvicorn](https://github.com/encode/uvicorn) — Encode
**License:** BSD

ASGI server.

### [httpx](https://github.com/encode/httpx) — Encode
**License:** BSD

Async HTTP client used for Ollama API calls and SSE pull streaming.

### [Pydantic](https://github.com/pydantic/pydantic) — Samuel Colvin & contributors
**License:** MIT

Request/response validation and settings.

### [Textual](https://github.com/Textualize/textual) — Textualize
**License:** MIT

The terminal UI (TUI) layer (used in `ag/tui/`).

### [Rich](https://github.com/Textualize/rich) — Textualize
**License:** MIT

Syntax-highlighted terminal output used throughout the CLI.

### [DuckDuckGo Search](https://github.com/deedy5/duckduckgo_search) — deedy5
**License:** MIT

Web search tool used by the researcher agent.

---

## Models & Inference

### [Ollama](https://github.com/ollama/ollama) — Ollama, Inc.
**License:** MIT

Local model runner. All inference goes through the Ollama `/api/chat` and `/api/pull` endpoints.

### [Falcon-Mamba 7B](https://huggingface.co/tiiuae/falcon-mamba-7b-instruct) — Technology Innovation Institute (TII)
**License:** TII Falcon-Mamba License 2.0

The pure-SSM (State Space Model / Mamba architecture) 7B model available as
`Hudson/falcon-mamba-instruct:7b-q4_0` on Ollama. No attention heads — 1M context window.

### [Mixtral 8×7B](https://huggingface.co/mistralai/Mixtral-8x7B-Instruct-v0.1) — Mistral AI
**License:** Apache 2.0

Sparse Mixture-of-Experts model available as `mixtral:8x7b` on Ollama.

### [Jamba Reasoning](https://ollama.com/sam860/jamba-reasoning) — sam860 / AI21 Labs
**License:** Apache 2.0

Hybrid Transformer + Mamba 3B model with tool-calling support.

---

## Fonts

### [JetBrains Mono](https://www.jetbrains.com/lp/mono/) — JetBrains
**License:** SIL Open Font License 1.1

Used in the Monaco editor and terminal panel.

---

## A note on provenance

This project started as a fork/extension of the **Antigravity** internal tool
and was pushed to GitHub as **Freeagenticide**.
The agent-zero derivation was not explicitly documented during initial development —
these credits correct that omission.

If you believe any attribution is missing or incorrect, please open an issue.
