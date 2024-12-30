import os
import subprocess
from validator import app

def build_css():
    """Build Tailwind CSS"""
    print("Building Tailwind CSS...")
    try:
        # Check if npm is installed
        subprocess.run(["npm", "--version"], check=True, capture_output=True)
        
        # Build CSS
        subprocess.run(["npm", "run", "build"], check=True)
        print("CSS built successfully!")
        
    except subprocess.CalledProcessError:
        print("Warning: npm not found. Please install Node.js and npm to build CSS.")
        print("CSS may not be properly styled.")
    except Exception as e:
        print(f"Warning: Failed to build CSS: {str(e)}")
        print("CSS may not be properly styled.")

if __name__ == '__main__':
    # Build CSS before starting the app
    build_css()
    
    # Get port from environment variable or use default
    port = int(os.environ.get('PORT', 8080))
    
    # Run the app
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True  # Set to False in production
    ) 
