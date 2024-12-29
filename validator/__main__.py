"""Main entry point for the validator package"""
import sys
from pathlib import Path

# Add the parent directory to the path so we can import the validator package
sys.path.append(str(Path(__file__).parent.parent))

from .cli import cli as cli_app

if __name__ == "__main__":
    cli_app() 