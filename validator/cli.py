from typing import Optional, List
import typer
from decimal import Decimal
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich import box
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
    """Get wallet balance and list UTXOs"""
    try:
        # Get balance info
        balance_info = wallet_manager.get_balance(name)
        
        # Get all UTXOs including frozen ones
        utxos = wallet_manager.get_utxos(name, include_frozen=True)
        
        if utxos:
            # Create UTXO table
            table = Table(title=f"UTXOs for {name}")
            table.add_column("Amount (BTC)", justify="right", style="cyan")
            table.add_column("TXID", style="magenta")
            table.add_column("Vout", justify="center")
            table.add_column("Address", style="green")
            table.add_column("Status", justify="center")
            table.add_column("Frozen", justify="center")
            
            # Sort UTXOs by amount in descending order
            utxos.sort(key=lambda x: x.amount, reverse=True)
            
            for utxo in utxos:
                # Format amount to 8 decimal places
                amount = f"{float(utxo.amount):10.8f}"
                
                # Determine status
                if utxo.frozen:
                    status = "Frozen"
                elif utxo.confirmations and utxo.confirmations > 0:
                    status = f"Confirmed ({utxo.confirmations})"
                else:
                    status = "Unconfirmed"
                
                # Add frozen emoji if UTXO is frozen
                frozen_indicator = "🔒" if utxo.frozen else ""
                
                table.add_row(
                    amount,
                    utxo.txid,
                    str(utxo.vout),
                    utxo.address,
                    status,
                    frozen_indicator
                )
            
            console.print(table)
            
            # Display total balance
            total_balance = sum(utxo.amount for utxo in utxos)
            frozen_balance = sum(utxo.amount for utxo in utxos if utxo.frozen)
            spendable_balance = total_balance - frozen_balance
            
            console.print("\n[bold]Balance Summary:[/bold]")
            console.print(f"[green]Total Balance:[/green] {total_balance:10.8f} BTC")
            console.print(f"[yellow]Frozen Balance:[/yellow] {frozen_balance:10.8f} BTC")
            console.print(f"[cyan]Spendable Balance:[/cyan] {spendable_balance:10.8f} BTC")
        else:
            console.print("[yellow]No UTXOs found[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

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
                amount: Optional[int] = typer.Option(1000, help="Amount in satoshis (default: 1000 sats, minimum: 546)"),
                fee_rate: Optional[float] = typer.Option(1.0, help="Fee rate in sat/vB. Default is 1.0 sat/vB"),
                memo: Optional[str] = typer.Option(None, help="Optional memo for the frozen UTXO")):
    """Create and freeze a UTXO with specific value in satoshis (minimum 546 sats to avoid dust)"""
    try:
        # Check for dust limit
        if amount < 546:
            raise ValueError("Amount must be at least 546 satoshis to avoid dust limit")
            
        # Check minimum fee rate
        if fee_rate < 1.0:
            raise ValueError("Fee rate must be at least 1.0 sat/vB")
            
        # Convert satoshis to BTC
        btc_amount = Decimal(str(amount)) / Decimal('100000000')
        txid = wallet_manager.create_and_freeze_utxo(name, btc_amount, memo=memo, fee_rate=fee_rate)
        console.print(f"\n[green]✅ UTXO created and frozen successfully![/green]")
        console.print(f"[yellow]TXID:[/yellow] {txid}")
        console.print(f"[yellow]Amount:[/yellow] {amount} sats ({btc_amount} BTC)")
        console.print(f"[yellow]Fee Rate:[/yellow] {fee_rate} sat/vB")
        if memo:
            console.print(f"[yellow]Memo:[/yellow] {memo}")
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def consolidate(name: str, 
               fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB. Default is 5 sat/vB")):
    """Consolidate all unfrozen UTXOs into a single UTXO"""
    try:
        txid = wallet_manager.consolidate_utxos(name, fee_rate=fee_rate)
        if txid:
            console.print(f"\n[green]✅ Successfully consolidated UTXOs![/green]")
            console.print(f"[yellow]Transaction ID:[/yellow] {txid}")
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@wallet.command()
def help():
    """Display help information for all wallet commands"""
    console.print("\n[bold cyan]🔐 Bitcoin Wallet CLI Commands[/bold cyan]\n")

    # Create a table for commands
    table = Table(
        title="Available Commands",
        box=box.ROUNDED,
        header_style="bold magenta",
        show_lines=True
    )
    
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Description", style="green")
    table.add_column("Usage Example", style="yellow")

    # Add command information
    commands = [
        (
            "create",
            "Create a new wallet",
            "wallet create <name> --network regtest --address-type segwit --address-count 1"
        ),
        (
            "list",
            "List all wallets",
            "wallet list"
        ),
        (
            "info",
            "Get wallet information",
            "wallet info <name>"
        ),
        (
            "generate",
            "Generate new addresses for a wallet",
            "wallet generate <name> --count 1"
        ),
        (
            "balance",
            "Get wallet balance and list UTXOs",
            "wallet balance <name>"
        ),
        (
            "send",
            "Send bitcoin to an address",
            "wallet send <name> <address> <amount> --fee-rate 5.0 --memo \"Payment\""
        ),
        (
            "network",
            "Display network-specific wallet information",
            "wallet network <name> --network-type regtest --address-type segwit"
        ),
        (
            "freeze-utxo",
            "Create and freeze a UTXO with specific value",
            "wallet freeze-utxo <name> --amount 1000 --fee-rate 1.0 --memo \"Frozen UTXO\""
        ),
        (
            "consolidate",
            "Consolidate all unfrozen UTXOs into a single UTXO",
            "wallet consolidate <name> --fee-rate 5.0"
        )
    ]

    for cmd, desc, usage in commands:
        table.add_row(cmd, desc, usage)

    console.print(table)

    # Add additional information
    console.print("\n[bold yellow]📝 Notes:[/bold yellow]")
    console.print("• All amounts are in BTC unless specified otherwise")
    console.print("• Fee rates are in satoshis per virtual byte (sat/vB)")
    console.print("• The default network is regtest for development purposes")
    console.print("• For frozen UTXOs, minimum amount is 546 satoshis to avoid dust")
    
    console.print("\n[bold green]🌐 Network Types:[/bold green]")
    console.print("• regtest: Local development network")
    console.print("• testnet: Bitcoin testnet for testing")
    console.print("• mainnet: Bitcoin mainnet (real network)")
    
    console.print("\n[bold blue]📋 Address Types:[/bold blue]")
    console.print("• segwit: Native SegWit (starts with bc1q/tb1q/bcrt1q)")
    console.print("• nested-segwit: Nested SegWit (starts with 3)")
    console.print("• legacy: Legacy addresses (starts with 1/m/n)")
    console.print("• taproot: Taproot addresses (starts with bc1p/tb1p/bcrt1p)")

    console.print("\n[bold magenta]💡 For more details on a specific command:[/bold magenta]")
    console.print("python3 -m validator wallet <command> --help")
    console.print("\n") 