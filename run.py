"""
Foresight - Stock Prediction Dashboard
Entry point for running the Flask application
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/home/coolhand/.env')
load_dotenv('.env')  # Local overrides

from app import create_app
from app.config import config

# Get environment
env = os.environ.get('FLASK_ENV', 'development')
app = create_app(config.get(env, config['default']))

if __name__ == '__main__':
    app.run(
        host=app.config['HOST'],
        port=app.config['PORT'],
        debug=app.config['DEBUG']
    )
