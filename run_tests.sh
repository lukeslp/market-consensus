#!/bin/bash
# Foresight test runner
# Provides convenient shortcuts for common test operations

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo -e "${RED}Error: Virtual environment not found${NC}"
    exit 1
fi

# Set PYTHONPATH (bundled llm_providers lives in project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Display usage
usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  all           Run all tests"
    echo "  fast          Run only fast tests (skip slow)"
    echo "  unit          Run unit tests only"
    echo "  integration   Run integration tests only"
    echo "  api           Run API tests only"
    echo "  db            Run database tests only"
    echo "  coverage      Run with coverage report"
    echo "  watch         Run tests on file changes (requires pytest-watch)"
    echo "  file FILE     Run specific test file"
    echo ""
    echo "Examples:"
    echo "  $0 all"
    echo "  $0 fast"
    echo "  $0 coverage"
    echo "  $0 file tests/test_api.py"
}

# No arguments - show usage
if [ $# -eq 0 ]; then
    usage
    exit 0
fi

case "$1" in
    all)
        echo -e "${GREEN}Running all tests...${NC}"
        pytest -v
        ;;

    fast)
        echo -e "${GREEN}Running fast tests (excluding slow)...${NC}"
        pytest -m "not slow" -v
        ;;

    unit)
        echo -e "${GREEN}Running unit tests...${NC}"
        pytest -m unit -v
        ;;

    integration)
        echo -e "${GREEN}Running integration tests...${NC}"
        pytest -m integration -v
        ;;

    api)
        echo -e "${GREEN}Running API tests...${NC}"
        pytest -m api -v
        ;;

    db)
        echo -e "${GREEN}Running database tests...${NC}"
        pytest -m database -v
        # Run legacy DB test script only if present
        if [ -f "test_db.py" ]; then
            echo -e "${GREEN}Running original test_db.py...${NC}"
            python test_db.py
        else
            echo -e "${YELLOW}Skipping legacy test_db.py (file not present)${NC}"
        fi
        ;;

    coverage)
        echo -e "${GREEN}Running tests with coverage...${NC}"
        pytest --cov=app --cov=db --cov-report=html --cov-report=term-missing
        echo -e "${GREEN}Coverage report generated: htmlcov/index.html${NC}"
        ;;

    watch)
        echo -e "${GREEN}Watching for changes...${NC}"
        if command -v ptw &> /dev/null; then
            ptw -v
        else
            echo -e "${YELLOW}pytest-watch not installed. Install with: pip install pytest-watch${NC}"
            exit 1
        fi
        ;;

    file)
        if [ -z "$2" ]; then
            echo -e "${RED}Error: Please specify test file${NC}"
            echo "Example: $0 file tests/test_api.py"
            exit 1
        fi
        echo -e "${GREEN}Running $2...${NC}"
        pytest "$2" -v
        ;;

    *)
        echo -e "${RED}Unknown option: $1${NC}"
        usage
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"
