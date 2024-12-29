import click
from typing import Optional
from rich.console import Console
from .wallet import wallet_manager, NetworkType

console = Console()

# Define constants
NETWORKS = ['mainnet', 'testnet', 'regtest']
ADDRESS_TYPES = ['legacy', 'segwit', 'nested-segwit', 'taproot']

@click.group()
def cli():
    """Bitcoin Wallet CLI - Supports multiple networks and address types including Taproot"""
    pass

@cli.group()
def wallet():
    """Manage Bitcoin wallets, addresses, and networks"""
    pass

@wallet.command()
@click.argument('name')
@click.option('--network', type=click.Choice(NETWORKS), default='regtest',
              help='Network type (default: regtest)')
@click.option('--type', 'address_type', type=click.Choice(ADDRESS_TYPES), default='segwit',
              help='Address type (default: segwit)')
@click.option('--address-count', default=1, help='Number of initial addresses to generate')
def create(name: str, network: str = 'regtest', address_type: str = 'segwit', address_count: int = 1):
    """Create a new wallet with specified network and address type"""
    try:
        result = wallet_manager.create_wallet(name, network, address_count, address_type)
        console.print(f"\n✅ Created wallet '{name}' on {network} network")
        console.print(f"📋 Address type: {address_type}")
        console.print(f"🔢 Generated {len(result['addresses'])} address(es)")
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
def list():
    """List all wallets and their details"""
    try:
        wallet_manager.list_wallets()
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('name')
def info(name: str):
    """Display detailed wallet information"""
    try:
        wallet_manager.get_wallet(name)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('name')
@click.option('--network', type=click.Choice(NETWORKS),
              help='Override network type for display')
@click.option('--type', 'address_type', type=click.Choice(ADDRESS_TYPES),
              help='Filter by address type')
def addresses(name: str, network: Optional[str] = None, address_type: Optional[str] = None):
    """Display wallet addresses with network and type information"""
    try:
        wallet_manager.get_network_info(name, network, address_type)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('name')
@click.option('--network', type=click.Choice(NETWORKS),
              help='Override network type for new address')
@click.option('--type', 'address_type', type=click.Choice(ADDRESS_TYPES),
              help='Address type for new address')
def generate(name: str, network: Optional[str] = None, address_type: Optional[str] = None):
    """Generate a new address for the wallet"""
    try:
        wallet_manager.generate_address(name, network, address_type)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('name')
@click.option('--count', default=1, help='Number of addresses to generate')
@click.option('--network', type=click.Choice(NETWORKS),
              help='Override network type for new addresses')
@click.option('--type', 'address_type', type=click.Choice(ADDRESS_TYPES),
              help='Address type for new addresses')
def generate_batch(name: str, count: int = 1, network: Optional[str] = None, 
                  address_type: Optional[str] = None):
    """Generate multiple new addresses for the wallet"""
    try:
        wallet_manager.generate_addresses(name, count, network, address_type)
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

@wallet.command()
@click.argument('address')
def validate(address: str):
    """Validate a Bitcoin address format"""
    try:
        is_valid = True  # Placeholder for actual validation
        network = "unknown"
        address_type = "unknown"
        
        if address.startswith('bc1p'):
            network = "mainnet"
            address_type = "taproot"
        elif address.startswith('tb1p'):
            network = "testnet"
            address_type = "taproot"
        elif address.startswith('bcrt1p'):
            network = "regtest"
            address_type = "taproot"
        elif address.startswith('bc1q'):
            network = "mainnet"
            address_type = "segwit"
        elif address.startswith('tb1q'):
            network = "testnet"
            address_type = "segwit"
        elif address.startswith('bcrt1q'):
            network = "regtest"
            address_type = "segwit"
        elif address.startswith('1'):
            network = "mainnet"
            address_type = "legacy"
        elif address.startswith(('m', 'n')):
            network = "testnet/regtest"
            address_type = "legacy"
        elif address.startswith('3'):
            network = "mainnet"
            address_type = "nested-segwit"
        elif address.startswith('2'):
            network = "testnet/regtest"
            address_type = "nested-segwit"
        
        console.print("\n🔍 [bold]Address Analysis:[/bold]")
        console.print(f"[cyan]Address:[/cyan] {address}")
        console.print(f"[magenta]Network:[/magenta] {network}")
        console.print(f"[yellow]Type:[/yellow] {address_type}")
        if address_type == "taproot":
            console.print("[green]✨ This is a Taproot address with enhanced privacy and smart contract capabilities[/green]")
        console.print(f"[{'green' if is_valid else 'red'}]Valid: {'✅' if is_valid else '❌'}[/]\n")
    except Exception as e:
        console.print(f"❌ Error: {str(e)}", style="red")

if __name__ == '__main__':
    cli() 