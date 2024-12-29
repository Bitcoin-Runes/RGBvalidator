import typer
import json
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.table import Table

from .database import Database
from .models import (
    FungibleToken, NonFungibleToken, TokenType,
    WalletInfo, UTXOReference
)
from .bitcoin_client import bitcoin_client

app = typer.Typer(help="Token Validator CLI")
wallet_app = typer.Typer(help="Wallet management commands")
token_app = typer.Typer(help="Token management commands")
app.add_typer(wallet_app, name="wallet")
app.add_typer(token_app, name="token")

db = Database()
console = Console()

# Wallet Commands
@wallet_app.command("create")
def create_wallet(
    wallet_name: str = typer.Argument(..., help="Name for the new wallet")
):
    """Create a new Bitcoin wallet"""
    try:
        wallet_info = bitcoin_client.create_wallet(wallet_name)
        wallet = WalletInfo(
            wallet_name=wallet_info["wallet_name"],
            address=wallet_info["address"],
            balance=0.0
        )
        db.store_wallet(wallet)
        console.print(f"[green]Successfully created wallet:[/green]")
        console.print(f"Wallet Name: {wallet.wallet_name}")
        console.print(f"Address: {wallet.address}")
    except Exception as e:
        console.print(f"[red]Error creating wallet: {str(e)}[/red]")
        raise typer.Exit(1)

@wallet_app.command("info")
def get_wallet_info(
    wallet_name: str = typer.Argument(..., help="Name of the wallet")
):
    """Get wallet information"""
    try:
        wallet = db.get_wallet(wallet_name)
        if not wallet:
            console.print(f"[red]Wallet not found: {wallet_name}[/red]")
            raise typer.Exit(1)
        
        balance = bitcoin_client.get_wallet_balance(wallet_name)
        db.update_wallet_balance(wallet_name, balance)
        
        console.print(f"[green]Wallet Information:[/green]")
        console.print(f"Name: {wallet.wallet_name}")
        console.print(f"Address: {wallet.address}")
        console.print(f"Balance: {balance} BTC")
    except Exception as e:
        console.print(f"[red]Error getting wallet info: {str(e)}[/red]")
        raise typer.Exit(1)

@wallet_app.command("list")
def list_wallets():
    """List all wallets"""
    try:
        wallets = db.list_wallets()
        if not wallets:
            console.print("[yellow]No wallets found[/yellow]")
            return

        table = Table(title="Wallets")
        table.add_column("Name", style="cyan")
        table.add_column("Address", style="magenta")
        table.add_column("Balance (BTC)", style="green")

        for wallet in wallets:
            table.add_row(
                wallet.wallet_name,
                wallet.address,
                str(wallet.balance)
            )
        
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error listing wallets: {str(e)}[/red]")
        raise typer.Exit(1)

@wallet_app.command("address")
def get_wallet_address(
    wallet_name: str = typer.Argument(..., help="Name of the wallet")
):
    """Get a new address for the wallet"""
    try:
        address = bitcoin_client.get_wallet_address(wallet_name)
        console.print(f"[green]New address for wallet {wallet_name}:[/green]")
        console.print(address)
    except Exception as e:
        console.print(f"[red]Error getting wallet address: {str(e)}[/red]")
        raise typer.Exit(1)

@wallet_app.command("utxos")
def list_utxos(
    wallet_name: str = typer.Argument(..., help="Name of the wallet")
):
    """List UTXOs for a wallet"""
    try:
        utxos = bitcoin_client.get_utxos(wallet_name)
        if not utxos:
            console.print(f"[yellow]No UTXOs found for wallet: {wallet_name}[/yellow]")
            return

        table = Table(title=f"UTXOs for {wallet_name}")
        table.add_column("TXID", style="cyan")
        table.add_column("VOUT", style="magenta")
        table.add_column("Amount (BTC)", style="green")

        for utxo in utxos:
            table.add_row(
                utxo["txid"],
                str(utxo["vout"]),
                str(utxo["amount"])
            )
        
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error listing UTXOs: {str(e)}[/red]")
        raise typer.Exit(1)

# Token Commands
@token_app.command("create-fungible")
def create_fungible_token(
    name: str = typer.Option(..., help="Token name"),
    description: str = typer.Option(None, help="Token description"),
    wallet_name: str = typer.Option(..., help="Wallet name"),
    txid: str = typer.Option(..., help="UTXO transaction ID"),
    vout: int = typer.Option(..., help="UTXO output index"),
    amount: float = typer.Option(..., help="UTXO amount"),
    total_supply: int = typer.Option(..., help="Total token supply"),
    decimals: int = typer.Option(18, help="Token decimals"),
    signature: Optional[str] = typer.Option(None, help="Token signature")
):
    """Create a new fungible token"""
    try:
        # Verify UTXO exists
        if not bitcoin_client.verify_utxo(txid, vout):
            console.print("[red]Invalid UTXO[/red]")
            raise typer.Exit(1)

        token = FungibleToken(
            name=name,
            description=description,
            token_type=TokenType.FUNGIBLE,
            wallet_name=wallet_name,
            utxo_ref=UTXOReference(txid=txid, vout=vout, amount=amount),
            total_supply=total_supply,
            decimals=decimals,
            signature=signature
        )
        
        db.store_token(token)
        console.print("[green]Successfully created fungible token:[/green]")
        console.print(json.dumps(token.dict(), indent=2))
    except Exception as e:
        console.print(f"[red]Error creating token: {str(e)}[/red]")
        raise typer.Exit(1)

@token_app.command("create-nft")
def create_non_fungible_token(
    name: str = typer.Option(..., help="Token name"),
    description: str = typer.Option(None, help="Token description"),
    wallet_name: str = typer.Option(..., help="Wallet name"),
    txid: str = typer.Option(..., help="UTXO transaction ID"),
    vout: int = typer.Option(..., help="UTXO output index"),
    amount: float = typer.Option(..., help="UTXO amount"),
    token_id: str = typer.Option(..., help="Unique token ID"),
    metadata_uri: Optional[str] = typer.Option(None, help="Metadata URI"),
    signature: Optional[str] = typer.Option(None, help="Token signature"),
    attributes_file: Optional[Path] = typer.Option(None, help="JSON file containing token attributes")
):
    """Create a new non-fungible token"""
    try:
        # Verify UTXO exists
        if not bitcoin_client.verify_utxo(txid, vout):
            console.print("[red]Invalid UTXO[/red]")
            raise typer.Exit(1)

        attributes = None
        if attributes_file:
            with open(attributes_file) as f:
                attributes = json.load(f)

        token = NonFungibleToken(
            name=name,
            description=description,
            token_type=TokenType.NON_FUNGIBLE,
            wallet_name=wallet_name,
            utxo_ref=UTXOReference(txid=txid, vout=vout, amount=amount),
            token_id=token_id,
            metadata_uri=metadata_uri,
            attributes=attributes,
            signature=signature
        )
        
        db.store_token(token)
        console.print("[green]Successfully created non-fungible token:[/green]")
        console.print(json.dumps(token.dict(), indent=2))
    except Exception as e:
        console.print(f"[red]Error creating token: {str(e)}[/red]")
        raise typer.Exit(1)

@token_app.command("get")
def get_token(
    txid: str = typer.Argument(..., help="UTXO transaction ID"),
    vout: int = typer.Argument(..., help="UTXO output index")
):
    """Get a token by its UTXO reference"""
    try:
        token = db.get_token_by_utxo(txid, vout)
        if not token:
            console.print("[red]Token not found[/red]")
            raise typer.Exit(1)
        
        console.print("[green]Token found:[/green]")
        console.print(json.dumps(token.dict(), indent=2))
    except Exception as e:
        console.print(f"[red]Error getting token: {str(e)}[/red]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app() 