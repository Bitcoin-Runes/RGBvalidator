import uvicorn
import typer
from typing import Optional

from .cli import app as cli_app
from .api import app as api_app

app = typer.Typer()

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8000, help="Port to bind to"),
    reload: bool = typer.Option(False, help="Enable auto-reload")
):
    """Start the validator API server"""
    uvicorn.run("validator.api:app", host=host, port=port, reload=reload)

@app.command()
def cli():
    """Run the validator CLI"""
    cli_app()

if __name__ == "__main__":
    app() 