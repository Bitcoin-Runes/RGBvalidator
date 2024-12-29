from typing import Optional, List
import typer
from decimal import Decimal
from rich.console import Console
from .wallet import wallet_manager

app = typer.Typer()
wallet = typer.Typer()
app.add_typer(wallet, name="wallet")
console = Console()

@wallet.command()
def create(name: str, 
          network: str = typer.Option("regtest", help="Network type: mainnet, testnet, or regtest"),
          address_type: str = typer.Option("segwit", help="Address type: legacy, segwit, nested-segwit, or taproot"),
          address_count: int = typer.Option(1, help="Number of initial addresses to generate")):
    """Create a new wallet"""
    try:
        wallet_manager.create_wallet(name, network=network, address_count=address_count, address_type=address_type)
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
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def balance(name: str):
    """Get wallet balance"""
    try:
        wallet_manager.get_balance(name)
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def send(name: str, address: str, amount: float, 
         memo: Optional[str] = typer.Option(None, help="Optional memo to include with the transaction"),
         fee_rate: Optional[float] = typer.Option(None, help="Fee rate in sat/vB. Default is 5 sat/vB for regtest")):
    """Send bitcoin to an address"""
    try:
        wallet_manager.send_bitcoin(name, address, Decimal(str(amount)), memo=memo, fee_rate=fee_rate)
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def network(name: str, network_type: Optional[str] = None, address_type: Optional[str] = None):
    """Display network-specific wallet information"""
    try:
        wallet_manager.get_network_info(name, network_type, address_type)
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def freeze_utxo(name: str, 
                amount: float,
                memo: Optional[str] = typer.Option(None, help="Optional memo for the frozen UTXO")):
    """Create and freeze a UTXO with specific value"""
    try:
        txid = wallet_manager.create_and_freeze_utxo(name, Decimal(str(amount)), memo=memo)
        console.print(f"\n[green]✅ UTXO created and frozen successfully![/green]")
        console.print(f"[yellow]TXID:[/yellow] {txid}")
        console.print(f"[yellow]Amount:[/yellow] {amount} BTC")
        if memo:
            console.print(f"[yellow]Memo:[/yellow] {memo}")
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]") 