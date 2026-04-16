# Freeagenticide

**A local-first agentic coding assistant with a live Monaco editor, Mamba model support, and agentic code execution.**

Built on [Antigravity](https://github.com/batteryphil/antigravity-local) — rebranded for self-hosting.

---

## What it does

- **Chat with any local Ollama model** — qwen2.5, llama3, Falcon-Mamba, Mixtral, and more
- **Agentic code execution** — ask "build me a snake game" and the agent writes the code into the Monaco editor and runs it in the terminal panel automatically
- **Live Monaco editor** — syntax highlighting, multi-language support, draggable terminal split
- **Streaming terminal** — stdout/stderr streamed live, HTML programs rendered in an iframe
- **Model manager** — browse, pull, delete, and switch models via a polished UI
- **Mamba SSM support** — `Hudson/falcon-mamba-instruct:7b-q4_0` (1M context, no attention)
- **Subprocess runner** — Python, JavaScript (Node), Bash, HTML all execute natively

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + uvicorn, async Python 3.11+ |
| Agent | ReAct-style tool loop (works with any model) |
| Inference | Ollama (`/api/chat` + `/api/pull` SSE) |
| Frontend | React 18 + Vite + Monaco Editor |
| Styling | Vanilla CSS (dark, glassmorphic) |
| Runner | asyncio subprocess + SSE streaming |

---

## Quick start

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/download) running locally
- Node.js 18+ (for UI rebuild, optional — pre-built dist is included)

```bash
# Clone
git clone https://github.com/batteryphil/freeagenticide.git
cd freeagenticide

# Backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Pull a model
ollama pull llama3

# Run
python -m uvicorn "ag.server.app:create_app" --factory --host 0.0.0.0 --port 7800
```

Open **http://localhost:7800** — the UI is served from `ui/dist/` by the FastAPI static file router.

---

## Rebuild the UI

```bash
cd ui
npm install
npm run build
```

---

## Agentic capabilities

The agent intercepts any code block the model produces (tagged or untagged) and:

1. **Writes** it to the Monaco editor (you see it appear with a `🤖 Agent` badge)
2. **Runs** it in the terminal panel (live stdout/stderr streamed)
3. **Reports** results back to the model so it can fix bugs and iterate

This works with **any model** — no native tool-calling support required.

### Agentic tools available to the model
| Tool | What it does |
|------|-------------|
| `write_to_editor` | Pushes code to Monaco — user sees it appear live |
| `run_in_ui` | Runs code, streams output to terminal, returns result to agent |
| `shell` | Execute shell commands |
| `file_ops` | Read / write files |
| `web_search` | Search the web |
| `code_exec` | Sandboxed Python execution |

---

## Model catalog (built-in)

| Model | Size | Architecture | Highlight |
|-------|------|-------------|-----------|
| `qwen2.5:0.5b` | 0.4 GB | Transformer | Minimal |
| `llama3.2:3b` | 2 GB | Transformer | Fast |
| `phi4-mini:3.8b` | 2.5 GB | Transformer | Best reasoning at this size |
| `qwen2.5:7b` | 4.7 GB | Transformer | Recommended |
| `Hudson/falcon-mamba-instruct:7b-q4_0` | 4.2 GB | **Mamba SSM** | 1M context, no attention |
| `mixtral:8x7b` | 26 GB | MoE | Multilingual powerhouse |

---

## Credits

The recursive multi-agent architecture (tool loop, `call_subordinate`, YAML agent profiles,
sub-agent spawning) is substantially derived from
**[agent-zero](https://github.com/frdel/agent-zero)** by Jan Mrázek (frdel) — MIT license.

Full attribution for all borrowed code, models, and libraries: **[CREDITS.md](CREDITS.md)**

---

## License

MIT
