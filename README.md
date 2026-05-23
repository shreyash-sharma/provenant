<p align="center">
  <img src="provenant.png" alt="Provenant" width="480"/>
</p>

**Attribution-guided wiki indexing for AI coding agents.**

Provenant indexes your codebase as LLM-generated wiki pages and retrieves them instead of raw source files — giving AI agents the right context in a fraction of the tokens.

```bash
pip install provenant
provenant init ./myrepo
```

---

## Results

Evaluated on **SWE-bench Verified** — 500 real GitHub issues across 12 Python repositories.

| Metric | Result |
|--------|--------|
| File Coverage@5 vs raw BM25 | **+24 percentage points** (63.8% vs ~40%) |
| File Coverage@10 with HyDE | **75.2%** |
| Token reduction vs naive file reading | **60–65×** |
| Answer quality delta (LLM judge) | **−0.15** (within noise) |

Full results and methodology: [`docs/RESULTS_SUMMARY.md`](docs/RESULTS_SUMMARY.md)

---

## How it works

`provenant init` reads your codebase once and writes a wiki — one page per file describing its purpose, public API, key functions, and relationships to other files. Pages are stored locally in `.provenant/`.

When an agent asks a question, Provenant searches the wiki instead of raw source code. Prose summaries match natural-language questions the way source code cannot.

After every answer, Provenant measures **attribution confidence** — which retrieved pages were actually cited. Low-confidence responses trigger automatic background repair of weak wiki pages. The index improves with use.

---

## Monorepo / Workspace Support

Point Provenant at a root folder containing multiple projects and it detects and indexes all of them:

```bash
provenant init ./my-project
# Detected 3 repositories:
#   backend/     (Django)
#   frontend/    (React/TypeScript)
#   mobile/      (React Native)
# Select repos to index: all
```

Each sub-repo gets its own wiki. Cross-repo context is linked so questions about the frontend can surface relevant backend files and vice versa.

---

## Features

### Wiki Indexing
`provenant init` parses your repo with tree-sitter, builds a symbol graph, and generates plain-English wiki pages for every file. Stored in `.provenant/`. No data leaves your machine except the LLM calls used to generate summaries.

### BM25 + HyDE Retrieval
Default retrieval is BM25 over wiki content. When enabled, Provenant generates a two-sentence hypothetical wiki snippet for the query, embeds it, and merges vector results with BM25 via Reciprocal Rank Fusion. Activates selectively — only when vector similarity is high.

```bash
provenant init ./myrepo                      # prompts for embedder
provenant init ./myrepo --embedder local     # free, ~40 MB, no API key
provenant init ./myrepo --embedder openai    # 768-dim, best retrieval
```

### Attribution Confidence
Every response includes a confidence score: `cited pages / retrieved pages`. Tracks index health over time. Low-confidence answers automatically trigger background wiki repair — no command needed.

### Automatic Self-Healing
When confidence falls below threshold, Provenant rewrites uncited wiki pages in the background. The answer returns immediately; repair happens concurrently. On a 1,393-page Django index, 3 of 4 low-confidence queries improved after repairing just 10 pages (~$0.02).

### MCP Server
Provenant exposes its tools as an MCP server for use with Claude, Cursor, and other AI editors.

```bash
provenant serve ./myrepo
```

Add to your MCP config:
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

## Quickstart

```bash
# Install
pip install provenant

# Index a single repo
provenant init ./myrepo

# Index a monorepo
provenant init ./my-project      # auto-detects subfolders

# Start MCP server
provenant serve ./myrepo

# Ask a question directly
provenant ask "how does authentication work?" --repo ./myrepo

# Check costs
provenant costs ./myrepo
```

---

## Configuration

Provenant reads from environment variables (`.env` in the repo root):

```bash
# LLM provider (one of)
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...

# Embedder (optional, enables vector search)
OPENAI_EMBEDDING_API_KEY=...
OPENAI_EMBEDDING_MODEL=nomic-embed-text-v1.5
OPENAI_EMBEDDING_BASE_URL=https://api.fireworks.ai/inference/v1

# Model overrides
PROVENANT_MODEL=deepseek/deepseek-chat
PROVENANT_DOC_MODEL=deepseek/deepseek-chat
```

---

## Paper

**Provenant: Attribution-Guided Wiki Indexing for Repository-Level AI Coding Agents**
Shreyash Sharma — Maulana Azad National Institute of Technology Bhopal

[Read the whitepaper →](https://www.shreyashsharma.com/writing/provenant)

---

## License

MIT
