#!/usr/bin/env bash
# Run this once to initialize the repo and push to GitHub
# Usage: ./init_repo.sh YOUR_GITHUB_USERNAME

set -e

USERNAME=${1:-"chauhanavi21"}
REPO="agentlens"

echo "🔭 Initializing AgentLens repo..."

git init
git add .
git commit -m "feat: initial release — AgentLens v0.1.0

- Python SDK: @trace, @span, @tool, @llm_call decorators
  - Zero dependencies, async support, budget guards
  - ConsoleExporter, FileExporter, HttpExporter
  - Auto-detects OpenAI/Anthropic token usage

- FastAPI server: ingest, query, analytics, run diff
  - PostgreSQL + JSONB storage with GIN indexes
  - POST /api/ingest/run, GET /api/runs, POST /api/runs/diff
  - /api/analytics/stats, slow-spans, model-usage

- React + D3 UI
  - Agent execution DAG with zoom/pan/click-to-inspect
  - Span drawer with inputs/outputs/LLM metadata
  - Run diff view: per-span duration delta, status changes
  - Analytics tab: slow spans bar chart, model cost breakdown
  - Demo mode (works without a running server)

- Docker Compose: one command to run everything
- Apache 2.0 license"

echo ""
echo "Creating GitHub repo: https://github.com/$USERNAME/$REPO"
echo "Make sure you have the GitHub CLI installed: brew install gh"
echo ""

# Create GitHub repo (requires gh auth login)
gh repo create "$USERNAME/$REPO" \
  --public \
  --description "Open source observability for AI agents — DAG graph, run diffing, budget guards" \
  --homepage "https://github.com/$USERNAME/$REPO"

# Add topics
gh repo edit "$USERNAME/$REPO" \
  --add-topic ai \
  --add-topic agents \
  --add-topic observability \
  --add-topic llm \
  --add-topic opentelemetry \
  --add-topic python \
  --add-topic self-hosted \
  --add-topic fastapi \
  --add-topic react

git remote add origin "git@github.com:$USERNAME/$REPO.git"
git push -u origin main

echo ""
echo "✅ Done! Repo is live at: https://github.com/$USERNAME/$REPO"
echo ""
echo "Next steps:"
echo "  1. Add a screenshot: docs/dag-screenshot.png"
echo "  2. Publish to PyPI: cd sdk && python -m build && twine upload dist/*"
echo "  3. Post to HN — copy the post from LAUNCH.md"
