#!/usr/bin/env python3

"""
Main entry point for the validator package.
"""

import sys
from .cli import app

if __name__ == "__main__":
    sys.exit(app()) 