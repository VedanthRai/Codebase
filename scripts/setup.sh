#!/bin/bash
# CodeOracle — Quick Start Script
set -e

echo "🔮 CodeOracle Setup"
echo "==================="

# Backend
echo ""
echo "📦 Setting up backend..."
cd backend
python -m venv .venv 2>/dev/null || true
source .venv/bin/activate

pip install -r requirements.txt -q

if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  Created .env — please add your GEMINI_API_KEY to backend/.env"
fi

mkdir -p data/repos data/chroma

echo "✓ Backend ready"

# Frontend
echo ""
echo "📦 Setting up frontend..."
cd ../frontend
npm install --silent
echo "✓ Frontend ready"

cd ..
echo ""
echo "✅ Setup complete!"
echo ""
echo "To start:"
echo "  Terminal 1: cd backend && source .venv/bin/activate && uvicorn api.main:app --reload --port 8000"
echo "  Terminal 2: cd frontend && npm run dev"
echo ""
echo "Then open: http://localhost:5173"
