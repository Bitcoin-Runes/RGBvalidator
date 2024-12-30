from flask import Flask
from pathlib import Path

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Change this in production

# Ensure data directories exist
BASE_DATA_DIR = Path("data")
WALLETS_DIR = BASE_DATA_DIR / "wallets"
NETWORK_DIR = BASE_DATA_DIR / "network"
TEMP_DIR = BASE_DATA_DIR / "temp"

for directory in [WALLETS_DIR, NETWORK_DIR, TEMP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Import routes after app initialization to avoid circular imports
from validator.web import *  # This imports all routes 