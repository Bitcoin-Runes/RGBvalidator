import click
from rich.console import Console
from rich.table import Table
from .wallet import wallet_manager
from .bitcoin_client import bitcoin_client

console = Console()

@click.group()
def cli():
    """Validator CLI tool"""
    pass

@cli.group()
def wallet():
    """Manage wallets"""
    pass

@wallet.command()
@click.argument('name')
def create(name: str):
    """Create a new wallet"""
    try:
        result = wallet_manager.create_wallet(name)
        console.print(f"✅ Created wallet '{name}'")
        console.print(f"📬 Address: {result['address']}")
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
def list():
    """List all wallets"""
    try:
        wallets = wallet_manager.list_wallets()
        if not wallets:
            console.print("No wallets found")
            return
        
        table = Table(title="Available Wallets")
        table.add_column("Name")
        table.add_column("First Address")
        
        for wallet_name in wallets:
            wallet_data = wallet_manager.get_wallet(wallet_name)
            if wallet_data and wallet_data.get('addresses'):
                table.add_row(wallet_name, wallet_data['addresses'][0])
            else:
                table.add_row(wallet_name, "No address")
        
        console.print(table)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('name')
def info(name: str):
    """Get wallet information"""
    try:
        wallet_data = wallet_manager.get_wallet(name)
        if not wallet_data:
            console.print(f"❌ Wallet '{name}' not found", style="red")
            return
        
        table = Table(title=f"Wallet: {name}")
        table.add_column("Property")
        table.add_column("Value")
        
        table.add_row("Created At", wallet_data.get('created_at', 'Unknown'))
        table.add_row("Address Count", str(len(wallet_data.get('addresses', []))))
        table.add_row("Latest Address", wallet_data.get('addresses', ['None'])[-1])
        
        console.print(table)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('name')
def new_address(name: str):
    """Generate a new address for the wallet"""
    try:
        address = wallet_manager.generate_address(name)
        console.print(f"✅ Generated new address for wallet '{name}'")
        console.print(f"📬 Address: {address}")
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

if __name__ == '__main__':
    cli() 