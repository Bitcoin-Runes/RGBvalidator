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
        balance_info = wallet_manager.get_balance(name, suppress_output=True)
        
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
               fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB. Default is 5 sat/vB"),
               batch_size: Optional[int] = typer.Option(50, help="Maximum number of UTXOs to consolidate in a single transaction")):
    """Consolidate all unfrozen UTXOs into a single UTXO"""
    try:
        # Get all UTXOs first to show summary
        utxos = wallet_manager.get_utxos(name, include_frozen=True)
        unfrozen_utxos = [u for u in utxos if not u.frozen]
        
        if len(unfrozen_utxos) < 2:
            console.print("[yellow]Need at least 2 unfrozen UTXOs to consolidate[/yellow]")
            return
        
        # Show consolidation summary
        console.print(f"\n[bold]Consolidation Summary:[/bold]")
        console.print(f"Total UTXOs: {len(utxos)}")
        console.print(f"Unfrozen UTXOs: {len(unfrozen_utxos)}")
        console.print(f"Frozen UTXOs: {len(utxos) - len(unfrozen_utxos)}")
        console.print(f"Batch Size: {batch_size}")
        console.print(f"Fee Rate: {fee_rate} sat/vB\n")
        
        # Calculate number of batches needed
        num_batches = (len(unfrozen_utxos) + batch_size - 1) // batch_size
        if num_batches > 1:
            console.print(f"[yellow]UTXOs will be consolidated in {num_batches} batches[/yellow]\n")
        
        # Process each batch
        successful_txids = []
        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(unfrozen_utxos))
            
            if num_batches > 1:
                console.print(f"[cyan]Processing batch {batch_num + 1} of {num_batches}...[/cyan]")
            
            try:
                txid = wallet_manager.consolidate_utxos(name, fee_rate=fee_rate, batch_size=batch_size)
                if txid:
                    successful_txids.append(txid)
                    console.print(f"[green]✅ Batch {batch_num + 1} consolidated successfully![/green]")
                    console.print(f"[yellow]Transaction ID:[/yellow] {txid}\n")
            except Exception as batch_error:
                console.print(f"[red]❌ Error in batch {batch_num + 1}: {str(batch_error)}[/red]")
                if "tx-size" in str(batch_error):
                    console.print("[yellow]Try reducing the batch size with --batch-size option[/yellow]")
                continue
        
        # Show final summary
        if successful_txids:
            console.print("\n[bold green]Consolidation Summary:[/bold green]")
            console.print(f"Successfully completed {len(successful_txids)} of {num_batches} batches")
            console.print("\n[yellow]Transaction IDs:[/yellow]")
            for i, txid in enumerate(successful_txids, 1):
                console.print(f"Batch {i}: {txid}")
        else:
            console.print("\n[red]No UTXOs were consolidated successfully[/red]")
            
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")
        if "tx-size" in str(e):
            console.print("[yellow]The transaction is too large. Try using a smaller batch size with --batch-size option[/yellow]")

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

@token.command()
def mint(
    wallet_name: str,
    name: str,
    symbol: str,
    decimals: int = typer.Option(6, help="Number of decimal places for the token"),
    description: Optional[str] = typer.Option(None, help="Optional description of the token"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Mint a new token"""
    try:
        # Create token data
        token_data = {
            "transaction_type": "mint20",
            "token": {
                "name": name,
                "symbol": symbol.upper(),
                "decimals": decimals,
                "description": description
            },
            "timestamp": "ISO-8601 timestamp",
            "version": "1.0"
        }

        # Create and freeze UTXO with the token data
        try:
            # Use a small amount for the UTXO (e.g., 1000 satoshis)
            amount = Decimal("0.00001000")  # 1000 satoshis
            memo = f"Token Mint: {symbol.upper()}"
            
            # Create the frozen UTXO
            txid = wallet_manager.create_and_freeze_utxo(
                wallet_name,
                amount,
                memo=memo,
                fee_rate=fee_rate
            )
            
            console.print(f"\n[green]Token minted successfully![/green]")
            console.print(f"[yellow]Token Name:[/yellow] {name}")
            console.print(f"[yellow]Symbol:[/yellow] {symbol.upper()}")
            console.print(f"[yellow]Decimals:[/yellow] {decimals}")
            if description:
                console.print(f"[yellow]Description:[/yellow] {description}")
            console.print(f"[yellow]TXID:[/yellow] {txid}")
            console.print("\n[bold cyan]Token minting UTXO has been frozen.[/bold cyan]")
            
        except Exception as e:
            raise ValueError(f"Failed to create token UTXO: {str(e)}")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@token.command()
def burn(
    wallet_name: str,
    symbol: str,
    amount: float,
    utxo: str = typer.Option(..., help="TXID of the token mint transaction"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Burn tokens"""
    try:
        # Verify the UTXO exists and is frozen
        utxos = wallet_manager.get_utxos(wallet_name, include_frozen=True)
        mint_utxo = next((u for u in utxos if u.txid == utxo and u.frozen), None)
        
        if not mint_utxo:
            raise ValueError(f"Token mint UTXO {utxo} not found or is not frozen")
        
        if not mint_utxo.memo or not mint_utxo.memo.startswith(f"Token Mint: {symbol.upper()}"):
            raise ValueError(f"UTXO {utxo} is not associated with token {symbol.upper()}")
        
        # Create burn transaction data
        burn_data = {
            "transaction_type": "burn20",
            "token": {
                "symbol": symbol.upper(),
            },
            "transactions": [{
                "type": "burn20",
                "amount": str(amount),
                "utxo": utxo
            }],
            "timestamp": "ISO-8601 timestamp",
            "version": "1.0"
        }

        # Create a new frozen UTXO for the burn
        try:
            # Use a small amount for the UTXO
            utxo_amount = Decimal("0.00001000")  # 1000 satoshis
            memo = f"Token Burn: {symbol.upper()} Amount: {amount}"
            
            # Create the frozen UTXO
            txid = wallet_manager.create_and_freeze_utxo(
                wallet_name,
                utxo_amount,
                memo=memo,
                fee_rate=fee_rate
            )
            
            console.print(f"\n[green]Tokens burned successfully![/green]")
            console.print(f"[yellow]Symbol:[/yellow] {symbol.upper()}")
            console.print(f"[yellow]Amount:[/yellow] {amount}")
            console.print(f"[yellow]Burn TXID:[/yellow] {txid}")
            console.print(f"[yellow]Original Mint TXID:[/yellow] {utxo}")
            
        except Exception as e:
            raise ValueError(f"Failed to create burn UTXO: {str(e)}")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@token.command()
def transfer(
    wallet_name: str,
    symbol: str,
    amount: float,
    recipient: str,
    utxo: str = typer.Option(..., help="TXID of the token mint transaction"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Transfer tokens to another address"""
    try:
        # Verify the UTXO exists and is frozen
        utxos = wallet_manager.get_utxos(wallet_name, include_frozen=True)
        mint_utxo = next((u for u in utxos if u.txid == utxo and u.frozen), None)
        
        if not mint_utxo:
            raise ValueError(f"Token mint UTXO {utxo} not found or is not frozen")
        
        if not mint_utxo.memo or not mint_utxo.memo.startswith(f"Token Mint: {symbol.upper()}"):
            raise ValueError(f"UTXO {utxo} is not associated with token {symbol.upper()}")
        
        # Create transfer transaction data
        transfer_data = {
            "transaction_type": "transfer20",
            "token": {
                "symbol": symbol.upper(),
            },
            "transactions": [{
                "type": "transfer20",
                "amount": str(amount),
                "utxo": utxo,
                "recipient": recipient
            }],
            "timestamp": "ISO-8601 timestamp",
            "version": "1.0"
        }

        # Create a new frozen UTXO for the transfer
        try:
            # Use a small amount for the UTXO
            utxo_amount = Decimal("0.00001000")  # 1000 satoshis
            memo = f"Token Transfer: {symbol.upper()} Amount: {amount} To: {recipient}"
            
            # Create the frozen UTXO
            txid = wallet_manager.create_and_freeze_utxo(
                wallet_name,
                utxo_amount,
                memo=memo,
                fee_rate=fee_rate
            )
            
            console.print(f"\n[green]Tokens transferred successfully![/green]")
            console.print(f"[yellow]Symbol:[/yellow] {symbol.upper()}")
            console.print(f"[yellow]Amount:[/yellow] {amount}")
            console.print(f"[yellow]Recipient:[/yellow] {recipient}")
            console.print(f"[yellow]Transfer TXID:[/yellow] {txid}")
            console.print(f"[yellow]Original Mint TXID:[/yellow] {utxo}")
            
        except Exception as e:
            raise ValueError(f"Failed to create transfer UTXO: {str(e)}")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@token.command()
def list(wallet_name: str):
    """List all tokens in the wallet"""
    try:
        # Get all frozen UTXOs
        utxos = wallet_manager.get_utxos(wallet_name, include_frozen=True)
        token_utxos = [u for u in utxos if u.frozen and u.memo and u.memo.startswith("Token")]
        
        if not token_utxos:
            console.print("[yellow]No tokens found in this wallet[/yellow]")
            return
        
        # Create a table for tokens
        table = Table(title=f"Tokens in Wallet: {wallet_name}")
        table.add_column("Symbol", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Amount", style="green")
        table.add_column("TXID", style="yellow")
        table.add_column("Memo", style="blue")
        
        for utxo in token_utxos:
            memo_parts = utxo.memo.split(": ")
            tx_type = memo_parts[0].replace("Token ", "")
            symbol = memo_parts[1].split(" ")[0] if len(memo_parts) > 1 else "Unknown"
            amount = memo_parts[1].split("Amount: ")[1].split(" ")[0] if "Amount: " in utxo.memo else "N/A"
            
            table.add_row(
                symbol,
                tx_type,
                amount if tx_type != "Mint" else "Supply",
                utxo.txid,
                utxo.memo
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]") 

@nft.command()
def mint(
    wallet_name: str,
    collection_name: str,
    token_id: str,
    name: str,
    description: Optional[str] = typer.Option(None, help="Description of the NFT"),
    attributes: Optional[str] = typer.Option(None, help="JSON string of attributes, e.g., '{\"color\": \"red\"}'"),
    media_url: Optional[str] = typer.Option(None, help="URL to the NFT media"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Mint a single NFT"""
    try:
        # Parse attributes if provided
        attr_dict = {}
        if attributes:
            try:
                attr_dict = json.loads(attributes)
            except json.JSONDecodeError:
                raise ValueError("Invalid JSON format for attributes")

        # Create NFT data
        nft_data = {
            "transaction_type": "mint721",  # ERC721 inspired
            "nft": {
                "collection": collection_name,
                "token_id": token_id,
                "name": name,
                "description": description,
                "attributes": attr_dict,
                "media_url": media_url
            },
            "timestamp": "ISO-8601 timestamp",
            "version": "1.0"
        }

        # Create and freeze UTXO with the NFT data
        try:
            amount = Decimal("0.00001000")  # 1000 satoshis
            memo = f"NFT Mint: {collection_name}#{token_id}"
            
            txid = wallet_manager.create_and_freeze_utxo(
                wallet_name,
                amount,
                memo=memo,
                fee_rate=fee_rate
            )
            
            console.print(f"\n[green]NFT minted successfully![/green]")
            console.print(f"[yellow]Collection:[/yellow] {collection_name}")
            console.print(f"[yellow]Token ID:[/yellow] {token_id}")
            console.print(f"[yellow]Name:[/yellow] {name}")
            if description:
                console.print(f"[yellow]Description:[/yellow] {description}")
            if attributes:
                console.print(f"[yellow]Attributes:[/yellow] {attributes}")
            if media_url:
                console.print(f"[yellow]Media URL:[/yellow] {media_url}")
            console.print(f"[yellow]TXID:[/yellow] {txid}")
            console.print("\n[bold cyan]NFT minting UTXO has been frozen.[/bold cyan]")
            
        except Exception as e:
            raise ValueError(f"Failed to create NFT UTXO: {str(e)}")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@nft.command()
def mint_batch(
    wallet_name: str,
    collection_name: str,
    batch_file: str = typer.Option(..., help="Path to JSON file containing batch NFT data"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Mint multiple NFTs from a batch file"""
    try:
        # Read and validate batch file
        try:
            with open(batch_file, 'r') as f:
                batch_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to read batch file: {str(e)}")

        if not isinstance(batch_data, list):
            raise ValueError("Batch file must contain a JSON array of NFT data")

        # Process each NFT in the batch
        minted_nfts = []
        for nft_item in batch_data:
            required_fields = ['token_id', 'name']
            if not all(field in nft_item for field in required_fields):
                raise ValueError(f"Missing required fields in NFT data: {required_fields}")

            # Create NFT data
            nft_data = {
                "transaction_type": "mint721_batch",
                "nft": {
                    "collection": collection_name,
                    "token_id": nft_item['token_id'],
                    "name": nft_item['name'],
                    "description": nft_item.get('description'),
                    "attributes": nft_item.get('attributes', {}),
                    "media_url": nft_item.get('media_url')
                },
                "timestamp": "ISO-8601 timestamp",
                "version": "1.0"
            }

            # Create and freeze UTXO for each NFT
            try:
                amount = Decimal("0.00001000")  # 1000 satoshis
                memo = f"NFT Mint Batch: {collection_name}#{nft_item['token_id']}"
                
                txid = wallet_manager.create_and_freeze_utxo(
                    wallet_name,
                    amount,
                    memo=memo,
                    fee_rate=fee_rate
                )
                
                minted_nfts.append({
                    "token_id": nft_item['token_id'],
                    "txid": txid
                })
                
            except Exception as e:
                console.print(f"[red]Failed to mint NFT {nft_item['token_id']}: {str(e)}[/red]")
                continue

        # Display results
        if minted_nfts:
            console.print(f"\n[green]Successfully minted {len(minted_nfts)} NFTs![/green]")
            
            table = Table(title=f"Minted NFTs in {collection_name}")
            table.add_column("Token ID", style="cyan")
            table.add_column("TXID", style="yellow")
            
            for nft in minted_nfts:
                table.add_row(nft['token_id'], nft['txid'])
            
            console.print(table)
        else:
            console.print("[red]No NFTs were minted successfully[/red]")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@nft.command()
def burn(
    wallet_name: str,
    collection_name: str,
    token_id: str,
    utxo: str = typer.Option(..., help="TXID of the NFT mint transaction"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Burn an NFT"""
    try:
        # Verify the UTXO exists and is frozen
        utxos = wallet_manager.get_utxos(wallet_name, include_frozen=True)
        nft_utxo = next((u for u in utxos if u.txid == utxo and u.frozen), None)
        
        if not nft_utxo:
            raise ValueError(f"NFT UTXO {utxo} not found or is not frozen")
        
        expected_memo_prefix = f"NFT Mint: {collection_name}#{token_id}"
        if not nft_utxo.memo or not nft_utxo.memo.startswith(expected_memo_prefix):
            raise ValueError(f"UTXO {utxo} is not associated with NFT {collection_name}#{token_id}")
        
        # Create burn transaction data
        burn_data = {
            "transaction_type": "burn721",
            "nft": {
                "collection": collection_name,
                "token_id": token_id
            },
            "timestamp": "ISO-8601 timestamp",
            "version": "1.0"
        }

        # Create a new frozen UTXO for the burn
        try:
            amount = Decimal("0.00001000")  # 1000 satoshis
            memo = f"NFT Burn: {collection_name}#{token_id}"
            
            txid = wallet_manager.create_and_freeze_utxo(
                wallet_name,
                amount,
                memo=memo,
                fee_rate=fee_rate
            )
            
            console.print(f"\n[green]NFT burned successfully![/green]")
            console.print(f"[yellow]Collection:[/yellow] {collection_name}")
            console.print(f"[yellow]Token ID:[/yellow] {token_id}")
            console.print(f"[yellow]Burn TXID:[/yellow] {txid}")
            console.print(f"[yellow]Original Mint TXID:[/yellow] {utxo}")
            
        except Exception as e:
            raise ValueError(f"Failed to create burn UTXO: {str(e)}")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@nft.command()
def transfer(
    wallet_name: str,
    collection_name: str,
    token_id: str,
    recipient: str,
    utxo: str = typer.Option(..., help="TXID of the NFT mint transaction"),
    fee_rate: Optional[float] = typer.Option(5.0, help="Fee rate in sat/vB"),
):
    """Transfer an NFT to another address"""
    try:
        # Verify the UTXO exists and is frozen
        utxos = wallet_manager.get_utxos(wallet_name, include_frozen=True)
        nft_utxo = next((u for u in utxos if u.txid == utxo and u.frozen), None)
        
        if not nft_utxo:
            raise ValueError(f"NFT UTXO {utxo} not found or is not frozen")
        
        expected_memo_prefix = f"NFT Mint: {collection_name}#{token_id}"
        if not nft_utxo.memo or not nft_utxo.memo.startswith(expected_memo_prefix):
            raise ValueError(f"UTXO {utxo} is not associated with NFT {collection_name}#{token_id}")
        
        # Create transfer transaction data
        transfer_data = {
            "transaction_type": "transfer721",
            "nft": {
                "collection": collection_name,
                "token_id": token_id,
                "recipient": recipient
            },
            "timestamp": "ISO-8601 timestamp",
            "version": "1.0"
        }

        # Create a new frozen UTXO for the transfer
        try:
            amount = Decimal("0.00001000")  # 1000 satoshis
            memo = f"NFT Transfer: {collection_name}#{token_id} To: {recipient}"
            
            txid = wallet_manager.create_and_freeze_utxo(
                wallet_name,
                amount,
                memo=memo,
                fee_rate=fee_rate
            )
            
            console.print(f"\n[green]NFT transferred successfully![/green]")
            console.print(f"[yellow]Collection:[/yellow] {collection_name}")
            console.print(f"[yellow]Token ID:[/yellow] {token_id}")
            console.print(f"[yellow]Recipient:[/yellow] {recipient}")
            console.print(f"[yellow]Transfer TXID:[/yellow] {txid}")
            console.print(f"[yellow]Original Mint TXID:[/yellow] {utxo}")
            
        except Exception as e:
            raise ValueError(f"Failed to create transfer UTXO: {str(e)}")

    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")

@nft.command()
def list(wallet_name: str, collection_name: Optional[str] = None):
    """List all NFTs in the wallet, optionally filtered by collection"""
    try:
        # Get all frozen UTXOs
        utxos = wallet_manager.get_utxos(wallet_name, include_frozen=True)
        nft_utxos = [u for u in utxos if u.frozen and u.memo and u.memo.startswith("NFT")]
        
        if not nft_utxos:
            console.print("[yellow]No NFTs found in this wallet[/yellow]")
            return
        
        # Filter by collection if specified
        if collection_name:
            nft_utxos = [u for u in nft_utxos if collection_name in u.memo]
            if not nft_utxos:
                console.print(f"[yellow]No NFTs found in collection: {collection_name}[/yellow]")
                return
        
        # Create a table for NFTs
        table = Table(title=f"NFTs in Wallet: {wallet_name}")
        table.add_column("Collection", style="cyan")
        table.add_column("Token ID", style="magenta")
        table.add_column("Type", style="green")
        table.add_column("TXID", style="yellow")
        table.add_column("Details", style="blue")
        
        for utxo in nft_utxos:
            memo_parts = utxo.memo.split(": ")
            tx_type = memo_parts[0].replace("NFT ", "")
            
            if tx_type == "Mint" or tx_type == "Mint Batch":
                collection_id = memo_parts[1].split("#")
                collection = collection_id[0]
                token_id = collection_id[1] if len(collection_id) > 1 else "Unknown"
                details = "Original Mint"
            elif tx_type == "Transfer":
                transfer_info = memo_parts[1].split(" To: ")
                collection_id = transfer_info[0].split("#")
                collection = collection_id[0]
                token_id = collection_id[1]
                details = f"Transferred to: {transfer_info[1]}"
            elif tx_type == "Burn":
                collection_id = memo_parts[1].split("#")
                collection = collection_id[0]
                token_id = collection_id[1]
                details = "Burned"
            else:
                collection = "Unknown"
                token_id = "Unknown"
                details = utxo.memo
            
            table.add_row(
                collection,
                token_id,
                tx_type,
                utxo.txid,
                details
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]") 

@app.command()
def cubaan(
    wallet_name: str,
    port: int = typer.Option(8000, help='Port to listen on'),
    is_bootstrap: bool = typer.Option(False, help='Run as a bootstrap node'),
    bootstrap_node: Optional[str] = typer.Option(None, help='Bootstrap node address (host:port)'),
    topic: str = typer.Option('wallet-sync', help='Topic for gossip protocol')
):
    """Experiment with DHT using the selected wallet. Can run as a bootstrap node or connect to an existing one."""
    try:
        # Get wallet instance
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            console.print(f"[red]Wallet {wallet_name} not found[/red]")
            return

        if is_bootstrap and bootstrap_node:
            console.print("[red]Error: Cannot be both a bootstrap node and connect to a bootstrap node[/red]")
            return

        # Run the async function
        asyncio.run(_cubaan_async(wallet, wallet_name, port, is_bootstrap, bootstrap_node, topic))

    except Exception as e:
        console.print(f"[red]Error in cubaan: {str(e)}[/red]")

async def _cubaan_async(wallet, wallet_name: str, port: int, is_bootstrap: bool, bootstrap_node: Optional[str], topic: str):
    """Async implementation of cubaan command"""
    try:
        # Create Kademlia DHT node
        dht_node = KademliaServer()
        await dht_node.listen(port)
        
        # Generate a unique node ID based on wallet name and port
        node_id = hashlib.sha256(f"{wallet_name}:{port}".encode()).hexdigest()[:16]
        
        if is_bootstrap:
            console.print(f"[green]Starting as bootstrap node[/green]")
            console.print(f"[green]Bootstrap Node ID: {node_id}[/green]")
            console.print(f"[green]Listening on port: {port}[/green]")
            console.print(f"[yellow]Other nodes can connect using: localhost:{port}[/yellow]")
        else:
            console.print(f"[green]Node started with ID: {node_id}[/green]")
            console.print(f"[green]Listening on port: {port}[/green]")

        # If this is not a bootstrap node, connect to the bootstrap node
        if bootstrap_node:
            console.print(f"[cyan]Attempting to connect to bootstrap node: {bootstrap_node}[/cyan]")
            try:
                host, bootstrap_port = bootstrap_node.split(':')
                await dht_node.bootstrap([(host, int(bootstrap_port))])
                console.print(f"[green]Successfully connected to bootstrap node: {bootstrap_node}[/green]")
            except Exception as e:
                console.print(f"[red]Failed to connect to bootstrap node: {str(e)}[/red]")
                console.print("[yellow]Continuing as a standalone node...[/yellow]")

        # Periodic wallet state broadcast and peer discovery
        async def broadcast_wallet_state():
            while True:
                try:
                    # Get wallet state to share
                    wallet_state = {
                        'node_id': node_id,
                        'wallet_name': wallet_name,
                        'network': wallet.network,
                        'balance': wallet.get_balance(),
                        'timestamp': time.time(),
                        'is_bootstrap': is_bootstrap
                    }
                    
                    # Store state in DHT
                    await dht_node.set(f"wallet:{node_id}", json.dumps(wallet_state))
                    console.print(f"\n[cyan]Stored wallet state in DHT: {wallet_state}[/cyan]")

                    # Get and display known peers from DHT
                    try:
                        peers = await dht_node.get("peers")
                        if peers:
                            peers = json.loads(peers)
                            console.print(f"[yellow]Known peers: {peers}[/yellow]")
                            
                            # Get other wallet states
                            for peer in peers:
                                if peer != node_id:
                                    peer_state = await dht_node.get(f"wallet:{peer}")
                                    if peer_state:
                                        state = json.loads(peer_state)
                                        role = "Bootstrap Node" if state.get('is_bootstrap') else "Peer"
                                        console.print(f"[blue]{role} {peer} state: {state}[/blue]")
                    except Exception as e:
                        console.print(f"[red]Error getting peer information: {str(e)}[/red]")
                    
                except Exception as e:
                    console.print(f"[red]Error broadcasting state: {str(e)}[/red]")
                
                await asyncio.sleep(10)  # Update every 10 seconds

        # Start broadcasting
        broadcast_task = asyncio.create_task(broadcast_wallet_state())

        # Store this node in peers list
        try:
            peers = await dht_node.get("peers")
            if peers:
                peers = json.loads(peers)
                if node_id not in peers:
                    peers.append(node_id)
            else:
                peers = [node_id]
            await dht_node.set("peers", json.dumps(peers))
            
            if is_bootstrap:
                await dht_node.set("bootstrap_node", node_id)
        except Exception as e:
            console.print(f"[red]Error storing peer information: {str(e)}[/red]")
            await dht_node.set("peers", json.dumps([node_id]))
            if is_bootstrap:
                await dht_node.set("bootstrap_node", node_id)

        # Handle graceful shutdown
        def signal_handler():
            broadcast_task.cancel()
            asyncio.create_task(dht_node.stop())

        # Register signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)

        # Keep the node running
        try:
            while True:
                cmd = input("\nEnter 'q' to quit, 'p' to print current DHT state, or 'b' to show bootstrap info: ")
                if cmd.lower() == 'q':
                    break
                elif cmd.lower() == 'p':
                    peers = await dht_node.get("peers")
                    if peers:
                        peers = json.loads(peers)
                        console.print(f"\n[yellow]Known peers: {peers}[/yellow]")
                        for peer in peers:
                            state = await dht_node.get(f"wallet:{peer}")
                            if state:
                                state_data = json.loads(state)
                                role = "Bootstrap Node" if state_data.get('is_bootstrap') else "Peer"
                                console.print(f"[blue]{role} {peer} state: {state_data}[/blue]")
                elif cmd.lower() == 'b':
                    bootstrap_id = await dht_node.get("bootstrap_node")
                    if bootstrap_id:
                        bootstrap_state = await dht_node.get(f"wallet:{bootstrap_id}")
                        if bootstrap_state:
                            console.print(f"[green]Bootstrap Node Information:[/green]")
                            console.print(f"[blue]{json.loads(bootstrap_state)}[/blue]")
                    else:
                        console.print("[yellow]No bootstrap node information found[/yellow]")
                await asyncio.sleep(1)
        finally:
            signal_handler()

    except Exception as e:
        console.print(f"[red]Error in cubaan: {str(e)}[/red]")
    finally:
        # Cleanup
        try:
            await dht_node.stop()
        except:
            pass

@app.command()
def lalai(
    wallet_name: str,
    port: int = typer.Option(8000, help='Port to listen on'),
    peers: str = typer.Option(None, help='Comma-separated list of peer addresses (e.g., localhost:8001,localhost:8002)'),
    topic: str = typer.Option('wallet-sync', help='Topic for gossip protocol')
):
    """Test gossip protocol functionality with the selected wallet."""
    try:
        # Get wallet instance
        wallet = wallet_manager.get_wallet(wallet_name)
        if not wallet:
            console.print(f"[red]Wallet {wallet_name} not found[/red]")
            return

        # Run the async function
        asyncio.run(_lalai_async(wallet, wallet_name, port, peers, topic))

    except Exception as e:
        console.print(f"[red]Error in lalai: {str(e)}[/red]")

async def _lalai_async(wallet, wallet_name: str, port: int, peers: Optional[str], topic: str):
    """Async implementation of lalai command"""
    try:
        # Initialize peer set and message cache
        peer_set: Set[str] = set()
        message_cache: Dict[str, float] = {}
        
        if peers:
            peer_set.update(peers.split(','))

        # Generate node ID
        node_id = hashlib.sha256(f"{wallet_name}:{port}".encode()).hexdigest()[:16]
        
        # Create web app for gossip protocol
        app = web.Application()
        routes = web.RouteTableDef()

        @routes.post('/gossip')
        async def handle_gossip(request):
            try:
                data = await request.json()
                msg_id = data.get('id')
                
                # Check if message is already seen
                if msg_id not in message_cache:
                    message_cache[msg_id] = time.time()
                    console.print(f"\n[blue]Received message from peer:[/blue]")
                    console.print(data)
                    
                    # Propagate to other peers (gossip)
                    asyncio.create_task(propagate_message(data, exclude_peer=str(request.remote)))
                
                return web.Response(text='OK')
            except Exception as e:
                return web.Response(text=str(e), status=500)

        app.add_routes(routes)
        
        # Start the server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', port)
        await site.start()
        
        console.print(f"[green]Node started with ID: {node_id}[/green]")
        console.print(f"[green]Listening on port: {port}[/green]")
        if peer_set:
            console.print(f"[green]Connected to peers: {peer_set}[/green]")

        async def propagate_message(message: dict, exclude_peer: Optional[str] = None):
            """Propagate message to all peers except the sender"""
            for peer in peer_set:
                if exclude_peer and peer in exclude_peer:
                    continue
                    
                try:
                    async with aiohttp.ClientSession() as session:
                        await session.post(f"http://{peer}/gossip", json=message)
                except Exception as e:
                    console.print(f"[red]Failed to propagate to {peer}: {str(e)}[/red]")

        async def broadcast_wallet_state():
            """Periodically broadcast wallet state"""
            while True:
                try:
                    # Create message with unique ID
                    message = {
                        'id': f"{node_id}:{random.randint(0, 1000000)}",
                        'node_id': node_id,
                        'wallet_name': wallet_name,
                        'network': wallet.network,
                        'balance': wallet.get_balance(),
                        'timestamp': time.time(),
                        'topic': topic
                    }
                    
                    # Broadcast to all peers
                    await propagate_message(message)
                    console.print(f"\n[cyan]Broadcasting wallet state: {message}[/cyan]")
                    
                except Exception as e:
                    console.print(f"[red]Error broadcasting state: {str(e)}[/red]")
                
                await asyncio.sleep(10)  # Broadcast every 10 seconds

        # Start broadcasting task
        broadcast_task = asyncio.create_task(broadcast_wallet_state())

        # Handle graceful shutdown
        def signal_handler():
            broadcast_task.cancel()
            asyncio.create_task(runner.cleanup())

        # Register signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)

        # Keep the node running
        try:
            while True:
                cmd = input("\nEnter 'q' to quit, 'p' to print peers, or 'm' to send custom message: ")
                if cmd.lower() == 'q':
                    break
                elif cmd.lower() == 'p':
                    console.print(f"\n[yellow]Connected peers: {peer_set}[/yellow]")
                elif cmd.lower() == 'm':
                    msg = input("Enter message to broadcast: ")
                    message = {
                        'id': f"{node_id}:{random.randint(0, 1000000)}",
                        'node_id': node_id,
                        'type': 'custom',
                        'content': msg,
                        'timestamp': time.time(),
                        'topic': topic
                    }
                    await propagate_message(message)
                    console.print(f"[green]Message sent: {message}[/green]")
                
                await asyncio.sleep(1)
        finally:
            signal_handler()

    except Exception as e:
        console.print(f"[red]Error in lalai: {str(e)}[/red]")
    finally:
        # Cleanup
        try:
            await runner.cleanup()
        except:
            pass

if __name__ == '__main__':
    app() 