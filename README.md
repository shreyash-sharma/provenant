<p align="center">
  <img src="provenant.png" alt="Provenant" width="460"/>
</p>

<p align="center">
  <strong>The codebase intelligence layer for your AI coding agent.</strong>
</p>

<p align="center">
  Wiki indexing &nbsp;·&nbsp; BM25 + HyDE retrieval &nbsp;·&nbsp; Self-healing index &nbsp;·&nbsp; Dead code &nbsp;·&nbsp; Risk &nbsp;·&nbsp; Git archaeology
</p>

<p align="center">
  <a href="https://pypi.org/project/provenant/"><img src="https://img.shields.io/pypi/v/provenant?color=blue&label=pypi" alt="PyPI"/></a>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License"/>
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python"/>
  <img src="https://img.shields.io/badge/MCP-compatible-orange" alt="MCP"/>
  <a href="https://github.com/shreyash-sharma/provenant"><img src="https://img.shields.io/github/stars/shreyash-sharma/provenant?style=social" alt="Stars"/></a>
</p>

<p align="center">
  <a href="https://www.shreyashsharma.com/writing/provenant"><strong>Read the whitepaper →</strong></a>
</p>

---

## 🏆 Performance

Evaluated on **SWE-bench Verified** — 500 real GitHub issues across 12 Python repositories.

| Metric | Baseline | + Provenant | Δ |
|--------|----------|-------------|---|
| File Coverage@5 | ~40% | **63.8%** | **+24 pp** |
| File Coverage@10 with HyDE | — | **75.2%** | — |
| Tokens vs naive file reading | baseline | — | **−60–65×** |
| Answer quality (LLM judge) | baseline | parity | **−0.15** (noise) |
| Low-confidence queries healed | — | **75%** | after one repair cycle |
| Cost per repair cycle | — | **~$0.02** | — |

---

## 🔧 MCP Tools

Eight tools, usable from Claude Code, Cursor, Windsurf, Cline, and Copilot:

| Tool | What it does |
|------|-------------|
| `provenant_ask` | Hybrid BM25 + HyDE retrieval → cited answer with confidence score |
| `provenant_context` | Triage cards for files, modules, symbols — purpose, API, freshness |
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

## ⚡ Quickstart

```bash
pip install provenant

provenant init ./myrepo        # index repo, generate wiki
provenant serve ./myrepo       # MCP server + web dashboard

provenant ask "how does auth work?" --repo ./myrepo
provenant costs ./myrepo
```

---

## 🧠 What Provenant Builds

Provenant runs once, builds everything, then keeps it in sync.

### ◆ Documentation Intelligence

`provenant init` parses your repo with tree-sitter across 15+ languages, builds a symbol + import graph, and generates plain-English wiki pages for every file — purpose, public API, key functions, relationships. Stored locally in `.provenant/`. Nothing leaves your machine except the LLM calls used to generate summaries.

When an agent asks a question, Provenant retrieves wiki pages instead of raw source. Prose matches natural-language queries the way code cannot.

### ◆ Attribution Confidence & Self-Healing

Every response computes `confidence = cited pages / retrieved pages`. Low-confidence answers automatically trigger background wiki repair — non-blocking, no command needed. On a 1,393-page Django index, rewriting just 10 pages fixed 75% of low-confidence queries at ~$0.02 total.

### ◆ Graph Intelligence

tree-sitter parses every file into a two-tier dependency graph — file nodes and symbol nodes (functions, classes, methods). Heritage extraction covers extends, implements, mixins, and trait impls across 15 languages. PageRank + betweenness centrality identify your most central and most coupled code.

### ◆ Dead Code Analysis

Identifies unreachable functions, classes, and modules. Groups by confidence tier (definite / likely / possible). Flags safe-to-delete vs. dynamically-called code. Works across Python, TypeScript, Go, Rust, and more.

### ◆ Risk Scoring

Change frequency × dependency centrality × test coverage gaps → per-file risk score. Know what breaks before you touch it.

### ◆ Git Archaeology

`provenant_why` traces why code exists: git blame, commit history, and architectural decisions linked to the files your agent is editing.

---

## 🗂️ Monorepo / Workspace Support

```bash
provenant init ./my-project
# Detected 3 repositories:
#   backend/     (Django)
#   frontend/    (React/TypeScript)
#   mobile/      (React Native)
```

Each sub-repo gets its own wiki. Cross-repo context is linked automatically — questions about the frontend surface relevant backend files and vice versa.

---

## 🖥️ Web Dashboard

```bash
provenant serve ./myrepo   # MCP server + local web UI
```

Visualize the knowledge graph, wiki pages, dead code report, risk scores, and repair candidates in a local browser dashboard. No external services required.

---

## ⚙️ Configuration

```bash
# LLM provider (pick one)
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...

# Embedder — optional, enables vector search + HyDE
OPENAI_EMBEDDING_API_KEY=...
OPENAI_EMBEDDING_MODEL=nomic-embed-text-v1.5
OPENAI_EMBEDDING_BASE_URL=https://api.fireworks.ai/inference/v1

# Embedding tiers
provenant init ./myrepo --embedder local     # free, ~40 MB, no API key
provenant init ./myrepo --embedder openai    # 768-dim, best retrieval
```

Self-hostable. Zero telemetry. Bring your own keys — works with Anthropic, OpenAI, DeepSeek, Gemini, OpenRouter, or local Ollama.

---

## 📄 License

MIT
