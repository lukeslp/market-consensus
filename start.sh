#!/bin/bash
# Foresight - Stock Prediction Dashboard
# Self-contained startup script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtualenv if present
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

# Load API keys from standard locations (first found wins)
for keyfile in "$SCRIPT_DIR/.env" "$HOME/documentation/API_KEYS.md" "$HOME/API_KEYS.md"; do
    if [ -f "$keyfile" ]; then
        source <(grep "^export" "$keyfile")
        break
    fi
done

# Ensure bundled llm_providers is on the path
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
export FLASK_ENV=production

# Enforce non-deprecated Anthropic model for this service runtime.

gunicorn -w 2 -b 0.0.0.0:5062 --timeout 120 --worker-class=gthread --threads=4 'run:app'
