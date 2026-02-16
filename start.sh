#!/bin/bash
cd /home/coolhand/projects/foresight
source venv/bin/activate
source <(grep "^export" /home/coolhand/documentation/API_KEYS.md)
export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH
export FLASK_ENV=production
gunicorn -w 2 -b 0.0.0.0:5062 --timeout 120 --worker-class=gthread --threads=4 'run:app'
