# PyRIT MCP Server

A modular [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that wraps
[Microsoft PyRIT](https://github.com/Azure/PyRIT) `0.14.0` and exposes **31 composable tools**
for **authorized** AI red-teaming — attack execution, scoring, prompt conversion, and result
inspection.

It is designed to be the "weapon store + scoring lab" component of a larger autonomous red-team
platform. Because it speaks standard MCP, any agent or MCP-capable host can drive it — for example a
[LangGraph](https://langchain-ai.github.io/langgraph/) agent that runs the attack loop and stores
findings. Instead of one monolithic endpoint, it offers small, independent tools that an agent can
freely combine inside a ReAct loop.

> ⚠️ **Authorized use only.** This project is for security research, CTF, and red-teaming of
> systems you own or are explicitly permitted to test. Do not use it against third-party systems
> without written authorization.

---

## Architecture

```
Any MCP agent / host  ──►  PyRIT MCP Server (this project)  ──►  target LLM(s)
  (the brain — e.g.          (attacks + scoring, 31 tools)        (victim / adversarial)
   LangGraph, Claude
   Desktop, custom loop)
```

```
pyrit_mcp_server/
├── main.py            # FastMCP instance + registers all tool modules
├── __main__.py        # python -m pyrit_mcp_server
├── core/
│   ├── memory.py      # CentralMemory singleton (idempotent, in-memory SQLite)
│   ├── targets.py     # TargetRegistry — create/get/remove OpenAI-compatible targets
│   └── jobs.py        # JobManager — background execution via asyncio.Task
└── tools/
    ├── targets.py     # 3 tools
    ├── attacks.py     # 11 tools (4 single-turn + 4 multi-turn + 3 job mgmt)
    ├── scoring.py     # 7 tools
    ├── converters.py  # 3 tools
    ├── scenarios.py   # 2 tools
    ├── datasets.py    # 2 tools
    └── memory_tools.py# 3 tools
```

### Key design decisions

- **Multi-turn attacks run in the background.** MCP tool calls would otherwise time out, so
  `red_team`, `crescendo`, `pair`, and `tap` return a `job_id` immediately and run as an
  `asyncio.Task`. Poll with `get_job_status` / `list_jobs`.
- **Token-cost guardrails.** Hard limits (`MAX_TURNS=30`, `MAX_TREE_WIDTH=10`,
  `MAX_TREE_DEPTH=15`, `MAX_BRANCHING=5`) are clamped on every attack to prevent runaway spend.
  `tap` also returns an estimated LLM-call count.
- **Two-stage hybrid scoring.** `score_hybrid` first runs a fast static check, then verifies with
  an LLM only if it triggers — reducing false positives.
- **Ephemeral memory by design.** PyRIT's own store is in-memory SQLite (`:memory:`); persistence
  is expected to live in the host platform, not here.

---

## The 31 tools

### Targets (3)
| Tool | Description |
|------|-------------|
| `create_target` | Create an OpenAI-compatible chat target (endpoint, model, api_key) |
| `list_targets` | List all registered targets |
| `remove_target` | Remove a target |

### Attacks — single-turn, synchronous (4)
| Tool | Description |
|------|-------------|
| `send_prompt` | Send a prompt directly (PromptSendingAttack) |
| `run_skeleton_key_attack` | Skeleton Key jailbreak |
| `run_flip_attack` | Flip-based jailbreak |
| `run_role_play_attack` | Role-play jailbreak (needs an adversarial LLM + scenario) |

### Attacks — multi-turn, background job (4)
| Tool | Description |
|------|-------------|
| `run_red_team_attack` | Adversarial LLM iteratively generates prompts |
| `run_crescendo_attack` | Gradual escalation attack |
| `run_pair_attack` | PAIR — Prompt Automatic Iterative Refinement |
| `run_tap_attack` | TAP — Tree of Attacks with Pruning (most expensive) |

### Attacks — job management (3)
| Tool | Description |
|------|-------------|
| `get_job_status` | Query a background job's status/result |
| `list_jobs` | List all jobs |
| `wait_for_job` | Block until a job finishes (or `timeout_seconds`), polling every `poll_interval_seconds` |

### Scoring (7)
| Tool | Type | Description |
|------|------|-------------|
| `score_likert` | LLM | 13 categories, float 0–1 (harm, violence, cyber, …) |
| `score_true_false` | LLM | 5 question types (task_achieved, prompt_injection, …) |
| `score_refusal` | LLM | Detect whether the AI refused |
| `score_substring` | non-LLM | Substring match |
| `score_regex` | non-LLM | Regex pattern match |
| `score_security` | non-LLM | 6 checks: xss, sql_injection, shell_command, path_traversal, credential_leak, markdown_injection |
| `score_hybrid` | hybrid | Static check + LLM verification (false-positive reduction) |

### Converters (3)
| Tool | Description |
|------|-------------|
| `convert_prompt` | Transform text with one converter (base64, rot13, leetspeak, …) |
| `chain_convert` | Apply several converters in sequence |
| `list_converters` | List available converters |

### Scenarios (2)
| Tool | Description |
|------|-------------|
| `list_scenarios` | List PyRIT built-in scenarios (AIRT, Garak, Foundry) |
| `run_scenario` | Run a built-in scenario (supports `max_objectives`) |

### Datasets (2)
| Tool | Description |
|------|-------------|
| `list_seed_datasets` | List PyRIT YAML seed datasets |
| `load_objectives` | Load seed objectives (with filtering) |

### Memory (3)
| Tool | Description |
|------|-------------|
| `get_attack_history` | Query attack history |
| `get_conversation` | Fetch a conversation by id |
| `export_results` | Export results as JSON |

---

## Requirements

- Python **3.11+**
- `pyrit==0.14.0`, `mcp>=1.27` (installed automatically)
- An OpenAI-compatible endpoint for the LLM targets — e.g. the OpenAI API or a local
  [Ollama](https://ollama.com) server (`http://127.0.0.1:11434/v1`).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# configure secrets
cp .env.example .env   # then edit .env and add your API key(s)
```

## Running

```bash
# as an installed entry point
pyrit-mcp-server

# or as a module
python -m pyrit_mcp_server
```

The server speaks MCP over stdio. Example client (e.g. Claude Desktop) config:

```json
{
  "mcpServers": {
    "pyrit": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "pyrit_mcp_server"]
    }
  }
}
```

### Typical flow

1. `create_target` for the victim (and one for the adversarial/scorer LLM).
2. Run an attack — `send_prompt` (sync) or `run_crescendo_attack` (returns a `job_id`).
3. For multi-turn jobs, poll `get_job_status` until `completed` / `failed`.
4. Score the response with `score_likert`, `score_refusal`, `score_security`, etc.
5. Inspect with `get_attack_history` / `export_results`.

---

## Example

[`examples/crescendo_attack.py`](examples/crescendo_attack.py) is a complete, runnable MCP client
that drives the server end-to-end against a local [Ollama](https://ollama.com) model
(`llama3.2:1b`): it spins up two targets (victim + adversarial), launches a `run_crescendo_attack`,
polls `get_job_status` until the job completes, then pulls the result via `get_attack_history` and
scores the last response with `score_security`.

```bash
# requires a local Ollama server running on http://127.0.0.1:11434
.venv/bin/python examples/crescendo_attack.py
```

It doubles as a smoke test: if it runs to completion and prints a result, the core
target → attack → job → history → scoring path is working. API keys for real OpenAI targets are
read from the environment (`OPENAI_API_KEY`) — never hardcode them.

---

## Known limitations

- **Concurrent multi-turn contention** — launching all four multi-turn attacks at once can leave
  jobs stuck in `running`. Run them sequentially.
- **Private-attribute coupling** — a couple of code paths reach into PyRIT internals
  (`OpenAIChatTarget._endpoint/_api_key`, a scenario's `_default_dataset_config`). These may break
  on a future PyRIT upgrade.
- **No job cleanup** — completed jobs/tasks are retained for the process lifetime (in-memory only).
- **`run_scenario` `max_objectives`** is honored by clamping the scenario's default dataset size;
  scenarios that don't expose that config silently ignore the limit.

---

## License

Released under the [MIT License](LICENSE). Built on top of Microsoft PyRIT, which is licensed
separately (MIT) by Microsoft.
