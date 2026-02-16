"""
Database Bridge for Foresight
Provides Flask integration for the ForesightDB class
"""
import sys
from pathlib import Path

# Add parent directory to path to import db.py
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from db import ForesightDB
from flask import g, current_app


def get_foresight_db():
    """Get ForesightDB instance from Flask g object"""
    if 'foresight_db' not in g:
        g.foresight_db = ForesightDB(current_app.config['DB_PATH'])
    return g.foresight_db


def close_foresight_db(e=None):
    """Close database connection (cleanup if needed)"""
    # ForesightDB uses context managers, no persistent connection to close
    g.pop('foresight_db', None)
