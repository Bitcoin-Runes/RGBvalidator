from typing import Optional, List, Dict, Set
import typer
from decimal import Decimal
import json
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box
from .wallet import wallet_manager
import asyncio
import click
import time
import os
import signal
from kademlia.network import Server as KademliaServer
import hashlib
import aiohttp
from aiohttp import web
import random
import webbrowser

app = typer.Typer()
wallet = typer.Typer()
token = typer.Typer()
nft = typer.Typer()
app.add_typer(wallet, name="wallet")
app.add_typer(token, name="token")
app.add_typer(nft, name="nft")
console = Console()

@wallet.command()
def create(name: str, 
          network: str = typer.Option("regtest", help="Network type: mainnet, testnet, or regtest"),
          address_type: str = typer.Option("taproot", help="Address type: legacy or taproot"),
          address_count: int = typer.Option(1, help="Number of initial addresses to generate")):
    """Create a new wallet"""
    try:
        # Validate address type
        if address_type not in ["legacy", "taproot"]:
            console.print("[red]❌ Error: Only legacy and taproot address types are supported[/red]")
            return
            
        wallet_manager.create_wallet(name, network=network, address_count=address_count, address_type=address_type)
        
        # Open the wallet detail page in the default browser
        wallet_url = f"http://localhost:5000/wallet/{name}"
        webbrowser.open(wallet_url)
        console.print(f"\n[green]✅ Wallet created successfully! Opening wallet page...[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def delete(name: str):
    """Delete a wallet permanently"""
    try:
        # Show warning and get confirmation
        console.print("\n[bold red]⚠️  WARNING: This action cannot be undone![/bold red]")
        console.print("[red]You are about to delete the following wallet permanently:[/red]")
        
        # Display wallet info
        wallet_info = wallet_manager.get_wallet(name)
        if not wallet_info:
            return
        
        # First confirmation
        confirm1 = typer.confirm("\nAre you sure you want to delete this wallet?")
        if not confirm1:
            console.print("[green]Operation cancelled.[/green]")
            return
            
        # Second confirmation with wallet name
        confirm2 = typer.prompt(
            "\n[red]Type the wallet name to confirm deletion[/red]",
            type=str
        )
        if confirm2 != name:
            console.print("[green]Operation cancelled: wallet name did not match.[/green]")
            return
            
        # Final confirmation
        confirm3 = typer.confirm(
            "\n[bold red]⚠️  FINAL WARNING: All wallet data will be permanently deleted. Continue?[/bold red]"
        )
        if not confirm3:
            console.print("[green]Operation cancelled.[/green]")
            return
            
        # Proceed with deletion
        wallet_manager.delete_wallet(name)
        console.print("\n[green]✅ Wallet deleted successfully.[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def list():
    """List all wallets"""
    try:
        wallet_manager.list_wallets()
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def info(name: str):
    """Get wallet information"""
    try:
        wallet_manager.get_wallet(name)
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def generate(name: str, count: int = typer.Option(1, help="Number of addresses to generate")):
    """Generate new addresses for a wallet"""
    try:
        wallet_manager.generate_addresses(name, count)
    except ValueError as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")
    except Exception as e:
        console.print(f"[red]❌ Unexpected error: {str(e)}[/red]") 