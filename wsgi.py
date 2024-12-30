import os
import subprocess
from validator import app

def build_css():
    """Build Tailwind CSS for production"""
    try:
        # Check if npm is installed
        subprocess.run(["npm", "--version"], check=True, capture_output=True)
        
        # Set NODE_ENV to production for optimized build
        env = dict(os.environ)
        env["NODE_ENV"] = "production"
        
        # Build CSS
        subprocess.run(["npm", "run", "build"], check=True, env=env)
        print("CSS built successfully for production!")
        
    except Exception as e:
        print(f"Warning: Failed to build CSS: {str(e)}")
        print("CSS may not be properly styled.")

# Build CSS when the file is loaded
build_css()

# Application entry point for WSGI servers
application = app 