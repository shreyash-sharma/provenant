<p align="center">
  <img src="provenant.png" alt="Provenant" width="480"/>
</p>

<p align="center">
  <strong>Attribution-guided codebase intelligence for AI coding agents.</strong><br/>
  Wiki indexing · BM25 + HyDE retrieval · Self-healing index · Dead code · Risk · Git archaeology
</p>

---

## Performance

Evaluated on **SWE-bench Verified** — 500 real GitHub issues across 12 Python repositories.

| Metric | Result |
|--------|--------|
| File Coverage@5 vs raw BM25 | **+24 pp** (63.8% → raw ~40%) |
| File Coverage@10 with HyDE | **75.2%** |
| Token reduction vs naive file reading | **60–65×** |
| Answer quality delta (LLM judge) | **−0.15** (within noise) |
| Self-healing: low-confidence queries improved | **75%** after one repair cycle |
| Cost per repair cycle | **~$0.02** |

---

## How It Works

`provenant init` parses your repo with tree-sitter, builds a symbol + import graph, and generates plain-English wiki pages for every file — one page per file describing its purpose, public API, key functions, and relationships. Pages are stored locally in `.provenant/`. No data leaves your machine except the LLM calls used to generate summaries.

When an agent asks a question, Provenant searches the wiki instead of raw source code. Prose summaries match natural-language queries the way source code cannot.

After every answer, Provenant computes **attribution confidence** — `cited pages / retrieved pages` — and automatically rewrites weak wiki pages in the background. The index improves with use.

---

## MCP Tools

Provenant exposes 8 tools via MCP, usable from Claude Code, Cursor, Windsurf, Cline, and Copilot:

| Tool | What it does |
|------|-------------|
| `provenant_ask` | Hybrid BM25 + HyDE retrieval → cited answer with confidence score |
| `provenant_context` | Triage cards for files, modules, and symbols — purpose, API, freshness |
| `provenant_search` | Semantic search over wiki content |
| `provenant_overview` | Architecture summary, entry points, dependency structure |
| `provenant_symbol` | Source bytes for a specific function or class |
| `provenant_dead_code` | Unreachable code with confidence tiers and safe-to-delete flags |
| `provenant_risk` | Hotspot scores, change frequency, test coverage gaps, blast radius |
| `provenant_why` | Architectural decisions and git archaeology — why does this code exist? |

```bash
provenant serve ./myrepo
```

```json
{
  "mcpServers": {
    "provenant": {
      "command": "provenant",
      "args": ["serve", "/path/to/repo"]
    }
  }
}
```

---

## Features

### Wiki Indexing
tree-sitter parses 15+ languages. One wiki page per file: purpose, public API, key functions, cross-file relationships. Stored in `.provenant/wiki.db`.

### BM25 + HyDE Retrieval
Default: BM25 over wiki content. With an embedder: Provenant generates a hypothetical wiki snippet for the query, embeds it, and merges vector results with BM25 via Reciprocal Rank Fusion.

```bash
provenant init ./myrepo                      # BM25 only
provenant init ./myrepo --embedder local     # free, ~40 MB, no API key
provenant init ./myrepo --embedder openai    # 768-dim, best retrieval
```

### Attribution Confidence & Self-Healing
Every response includes `confidence = cited / retrieved`. When it falls below threshold, Provenant rewrites uncited wiki pages in the background — non-blocking, no command needed. On a 1,393-page Django index, 10 targeted page rewrites fixed 75% of low-confidence queries at ~$0.02 total.

### Dead Code Analysis
Identifies unreachable functions, classes, and modules across Python, TypeScript, Go, and more. Groups by confidence tier. Flags safe-to-delete vs. dynamically-called code.

### Risk Scoring
Change frequency × dependency centrality × test coverage gaps → per-file risk score. Useful before refactoring or reviewing a PR.

### Git Archaeology
`provenant_why` traces why code exists: links git blame, commit history, and architectural decisions to the files an agent is currently editing.

### Monorepo / Workspace Support
```bash
provenant init ./my-project
# Detected 3 repositories:
#   backend/     (Django)
#   frontend/    (React/TypeScript)
#   mobile/      (React Native)
```
Each sub-repo gets its own wiki. Cross-repo context is linked automatically.

### Web Dashboard
```bash
provenant serve ./myrepo   # starts MCP server + web UI
```
Visualize the wiki, knowledge graph, dead code report, risk scores, and repair candidates in a local browser dashboard. No external services.

---

## Quickstart

```bash
pip install provenant

provenant init ./myrepo        # index repo, generate wiki
provenant serve ./myrepo       # MCP server + web dashboard

provenant ask "how does authentication work?" --repo ./myrepo
provenant costs ./myrepo       # token usage and spend
```

---

## Configuration

```bash
# LLM provider (pick one)
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...

# Embedder — optional, enables vector search + HyDE
OPENAI_EMBEDDING_API_KEY=...
OPENAI_EMBEDDING_MODEL=nomic-embed-text-v1.5
OPENAI_EMBEDDING_BASE_URL=https://api.fireworks.ai/inference/v1

# Model overrides
PROVENANT_MODEL=deepseek/deepseek-chat
```

Self-hostable. Zero telemetry. Bring your own keys — works with Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, or local Ollama.

---

## Paper

**Provenant: Attribution-Guided Wiki Indexing for Repository-Level AI Coding Agents**
Shreyash Sharma — Maulana Azad National Institute of Technology Bhopal

[Read the whitepaper →](https://www.shreyashsharma.com/writing/provenant)

---

## License

MIT
