#!/bin/bash
# ═══════════════════════════════════════════
# JARVIS v3.0 — One-Click Launcher
# ═══════════════════════════════════════════

set -e

echo "🚀 JARVIS v3.0 — Starting..."

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Install Python 3.10+ first.${NC}"
    exit 1
fi

# Check .env
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating from template...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}📝 Edit .env file and add your GROQ_API_KEY${NC}"
    exit 1
fi

# Check venv
if [ ! -d "venv" ]; then
    echo -e "${BLUE}📦 Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
echo -e "${BLUE}🔌 Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "${BLUE}📥 Installing dependencies...${NC}"
pip install -q -r requirements.txt


# Start server
echo -e "${GREEN}✅ JARVIS v3.0 is ready!${NC}"
echo -e "${GREEN}🌐 Server: http://localhost:8000${NC}"
echo -e "${GREEN}📚 API Docs: http://localhost:8000/docs${NC}"
echo ""

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
