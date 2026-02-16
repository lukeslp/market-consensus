"""
Foresight API Server - DEPRECATED
This file is kept for backward compatibility.
Use run.py as the entry point instead.
"""
import sys
import warnings

warnings.warn(
    "app.py is deprecated. Use 'python run.py' or 'gunicorn run:app' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Import the application factory
from run import app

if __name__ == '__main__':
    app.run(
        host=app.config['HOST'],
        port=app.config['PORT'],
        debug=app.config['DEBUG']
    )
