#!/usr/bin/env bash
set -euo pipefail

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# JobScout — One-command setup + GitHub push
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REPO_NAME="${1:-job-scout}"
GITHUB_USER="${2:-}"

echo "🎯 JobScout Setup"
echo "─────────────────────────────────────────"

# 1. Python dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt 2>/dev/null || pip install -r requirements.txt --break-system-packages

# 2. Verify
echo "🔍 Verifying installation..."
python -c "
from config.company_registry import COMPANY_REGISTRY, get_companies_by_priority
from scrapers.factory import ScraperFactory
from core.relevance_engine import RelevanceEngine
print(f'  ✅ {len(COMPANY_REGISTRY)} companies registered')
print(f'  ✅ Relevance engine ready ({len(RelevanceEngine().profile.skills)} skills)')
print(f'  ✅ Scraper factory ready')
"

# 3. Create .env if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 Created .env from template — edit with your email settings"
fi

# 4. Git init + GitHub push
echo ""
echo "📂 Initializing Git repository..."
git init -b main 2>/dev/null || git init && git checkout -b main 2>/dev/null || true
git add -A
git commit -m "feat: JobScout — self-recovering job pipeline

- Direct ATS integrations (Greenhouse, Lever, Ashby, SmartRecruiters, Workday)
- Custom scrapers for Google, Amazon, Apple, Microsoft, Meta, Bloomberg
- 100+ company registry with priority tiers
- Weighted relevance scoring engine (title/skills/location/company/salary)
- Circuit breaker self-recovery per company
- Email digest notifications for high-relevance matches
- Health monitoring API on :8089
- Docker + Fly.io + Render + Railway deployment configs
- GitHub Actions CI pipeline" 2>/dev/null || echo "  (already committed)"

if [ -n "$GITHUB_USER" ]; then
    echo ""
    echo "🚀 Pushing to GitHub..."
    gh repo create "$GITHUB_USER/$REPO_NAME" --public --source=. --push 2>/dev/null || {
        echo "  Creating remote and pushing..."
        git remote add origin "https://github.com/$GITHUB_USER/$REPO_NAME.git" 2>/dev/null || true
        git push -u origin main
    }
    echo "  ✅ https://github.com/$GITHUB_USER/$REPO_NAME"
else
    echo ""
    echo "💡 To push to GitHub, run ONE of:"
    echo ""
    echo "  # Option A: GitHub CLI (recommended)"
    echo "  gh repo create $REPO_NAME --public --source=. --push"
    echo ""
    echo "  # Option B: Manual"
    echo "  git remote add origin https://github.com/YOUR_USER/$REPO_NAME.git"
    echo "  git push -u origin main"
fi

echo ""
echo "─────────────────────────────────────────"
echo "✅ Setup complete! Next steps:"
echo ""
echo "  1. Edit .env with email settings (optional)"
echo "  2. Test:    python main.py --once"
echo "  3. Stats:   python main.py --stats"
echo "  4. Run:     python main.py"
echo "  5. Deploy:  fly launch  OR  docker compose up -d"
echo ""
