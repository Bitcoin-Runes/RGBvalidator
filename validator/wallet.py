from typing import Dict, List, Optional, Any, Union
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
import os
import json
import logging
import datetime
from pathlib import Path
from hdwallet import HDWallet
from hdwallet.symbols import BTC
from hdwallet.cryptocurrencies import BitcoinMainnet, BitcoinTestnet
from hdwallet.utils import generate_mnemonic
from cryptography.fernet import Fernet
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from .config import get_settings

settings = get_settings()
console = Console()

# Define network types
NetworkType = Literal["mainnet", "testnet", "regtest"]

def format_wallet_info(wallet_data: Dict) -> str:
    """Format wallet data for display"""
    return (
        f"Wallet: {wallet_data['name']}\n"
        f"Network: {wallet_data.get('network', 'mainnet')}\n"
        f"Addresses: {', '.join(wallet_data['addresses'])}"
    )

def display_wallet(wallet: Dict) -> None:
    """Display wallet info in a panel with clear address information"""
    text = Text()
    text.append(f"Name: {wallet['name']}\n", style="bold cyan")
    text.append(f"Network: {wallet.get('network', 'mainnet')}\n", style="magenta")
    text.append(f"Address Type: {wallet.get('address_type', 'legacy')}\n", style="yellow")
    text.append("\nReceiving Addresses:\n", style="bold green")
    
    for i, addr in enumerate(wallet['addresses']):
        text.append(f"  Address {i}: ", style="yellow")
        text.append(f"{addr}\n", style="white")
    
    text.append("\nDerivation Paths:\n", style="bold blue")
    network = wallet.get('network', 'mainnet')
    address_type = wallet.get('address_type', 'legacy')
    coin_type = "0" if network == "mainnet" else "1"
    
    # Get the correct path prefix based on address type
    if address_type == 'segwit':
        path_prefix = f"m/84'/{coin_type}'/0'/0"
    elif address_type == 'nested-segwit':
        path_prefix = f"m/49'/{coin_type}'/0'/0"
    else:
        path_prefix = f"m/44'/{coin_type}'/0'/0"
    
    for i in range(len(wallet['addresses'])):
        text.append(f"  Path {i}: ", style="yellow")
        text.append(f"{path_prefix}/{i}\n", style="white")
    
    # Add network-specific information
    text.append("\nNetwork Information:\n", style="bold magenta")
    if network == "regtest":
        text.append("- Using Regtest/Polar network (local development)\n", style="green")
        text.append("- Addresses can be funded using Polar's mining controls\n", style="green")
    elif network == "testnet":
        text.append("- Using Testnet network (testing)\n", style="yellow")
        text.append("- Get testnet coins from faucet: https://testnet-faucet.mempool.co/\n", style="green")
    else:
        text.append("- Using Mainnet network (production)\n", style="red")
        text.append("- WARNING: Uses real Bitcoin, verify addresses carefully\n", style="red")
    
    title = f"Wallet Information - {network.upper()} ({address_type})"
    console.print(Panel(text, title=title))

def display_wallets(wallets: List[Dict]) -> None:
    """Display wallets in a formatted table"""
    if not wallets:
        console.print("[yellow]No wallets found[/yellow]")
        return

    table = Table(title="Available Wallets")
    table.add_column("Name", style="cyan")
    table.add_column("Network", style="magenta")
    table.add_column("Addresses", style="green")
    
    for wallet in wallets:
        table.add_row(
            wallet["name"],
            wallet.get("network", "mainnet"),
            "\n".join(wallet["addresses"])
        )
    
    console.print(table)

def display_network_addresses(wallet: Dict, filter_type: Optional[str] = None) -> None:
    """Display wallet addresses grouped by network with format information"""
    text = Text()
    network = wallet.get('network', 'mainnet')
    address_type = wallet.get('address_type', 'legacy')
    
    text.append(f"\n{'='*50}\n", style="white")
    text.append(f"WALLET: {wallet['name'].upper()}\n", style="bold cyan")
    text.append(f"NETWORK: {network.upper()}\n", style="bold magenta")
    text.append(f"TYPE: {address_type.upper()}\n", style="bold yellow")
    text.append(f"{'='*50}\n\n", style="white")
    
    text.append("🔐 [bold]RECEIVING ADDRESSES[/bold]\n\n", style="green")
    
    for i, addr in enumerate(wallet['addresses']):
        # Skip if filtering by type and doesn't match
        if filter_type:
            addr_type = get_address_type(addr)
            if addr_type != filter_type:
                continue
        
        text.append(f"Address #{i+1}:\n", style="yellow")
        text.append(f"Network: {network}\n", style="magenta")
        text.append(f"Type: {get_address_type(addr)}\n", style="cyan")
        text.append(f"Address: {addr}\n", style="white")
        text.append(f"Path: {get_derivation_path(network, address_type, i)}\n", style="blue")
        text.append("\n")
    
    text.append(f"{'='*50}\n", style="white")
    text.append("\n💡 [bold]Usage Tips:[/bold]\n", style="yellow")
    
    if network == "regtest":
        text.append("- Use Polar's mining controls to fund addresses\n", style="green")
        text.append("- Perfect for development and testing\n", style="green")
    elif network == "testnet":
        text.append("- Get testnet coins from a faucet: https://testnet-faucet.mempool.co/\n", style="green")
        text.append("- Monitor transactions: https://mempool.space/testnet/\n", style="green")
    else:
        text.append("- Always verify the address before sending funds\n", style="red")
        text.append("- Keep your wallet backup secure\n", style="red")
        text.append("- Monitor transactions: https://mempool.space/\n", style="green")
    
    console.print(Panel(text, title=f"🏦 Bitcoin {network.upper()} Wallet"))

def get_address_type(address: str) -> str:
    """Determine address type from format"""
    if address.startswith(('bc1p', 'tb1p', 'bcrt1p')):
        return 'taproot'
    elif address.startswith(('bc1q', 'tb1q', 'bcrt1q')):
        return 'segwit'
    elif address.startswith(('3', '2')):
        return 'nested-segwit'
    else:
        return 'legacy'

def get_derivation_path(network: str, address_type: str, index: int) -> str:
    """Get full derivation path"""
    coin_type = "0" if network == "mainnet" else "1"
    if address_type == 'taproot':
        return f"m/86'/{coin_type}'/0'/0/{index}"  # BIP386 for Taproot
    elif address_type == 'segwit':
        return f"m/84'/{coin_type}'/0'/0/{index}"  # BIP84 for Native SegWit
    elif address_type == 'nested-segwit':
        return f"m/49'/{coin_type}'/0'/0/{index}"  # BIP49 for Nested SegWit
    else:
        return f"m/44'/{coin_type}'/0'/0/{index}"  # BIP44 for Legacy

class WalletManager:
    """Manages HD wallets with local key storage and encryption"""
    
    def __init__(self):
        self.wallets_dir = Path("data/wallets")
        self.wallets_dir.mkdir(parents=True, exist_ok=True)
        self._init_encryption()
        self.network = getattr(settings, "bitcoin_network", "mainnet")
    
    def _init_encryption(self):
        """Initialize encryption for wallet data"""
        key_file = Path("data/wallet.key")
        if not key_file.exists():
            key = Fernet.generate_key()
            key_file.write_bytes(key)
        self.fernet = Fernet(key_file.read_bytes())
    
    def _validate_wallet_name(self, name: Any) -> str:
        """Validate and normalize wallet name"""
        if isinstance(name, dict):
            name = name.get('name')
        if not isinstance(name, str):
            raise ValueError(f"Invalid wallet name type: {type(name)}")
        if not name:
            raise ValueError("Wallet name cannot be empty")
        return name
    
    def _get_network_path(self, network: NetworkType) -> str:
        """Get BIP44 coin type based on network"""
        coin_type = "0" if network == "mainnet" else "1"
        return f"m/44'/{coin_type}'/0'/0/0"
    
    def _get_derivation_path(self, network: NetworkType, address_type: str, index: int) -> str:
        """Get derivation path based on network and address type"""
        coin_type = "0" if network == "mainnet" else "1"
        # Different paths for different address types
        if address_type == 'segwit':
            # BIP84 for native SegWit
            return f"m/84'/{coin_type}'/0'/0/{index}"
        elif address_type == 'nested-segwit':
            # BIP49 for nested SegWit
            return f"m/49'/{coin_type}'/0'/0/{index}"
        else:
            # BIP44 for legacy addresses
            return f"m/44'/{coin_type}'/0'/0/{index}"
    
    def _get_address_for_type(self, wallet: HDWallet, network: NetworkType, address_type: str) -> str:
        """Generate address based on network and address type"""
        try:
            # Always clean derivation before generating address
            wallet.clean_derivation()
            
            # Set network type first
            if network == "mainnet":
                wallet.cryptocurrency = BitcoinMainnet
                is_testnet = False
            else:
                wallet.cryptocurrency = BitcoinTestnet
                is_testnet = True
            
            # Generate address based on type
            if address_type == 'taproot':
                address = wallet.p2tr_address()
                # Handle regtest conversion
                if network == "regtest":
                    if address.startswith("tb1p"):
                        address = "bcrt1p" + address[4:]
                    elif address.startswith("bc1p"):
                        address = "bcrt1p" + address[4:]
            
            elif address_type == 'segwit':
                address = wallet.p2wpkh_address()
                # Handle regtest conversion
                if network == "regtest":
                    if address.startswith("tb1q"):
                        address = "bcrt1q" + address[4:]
                    elif address.startswith("bc1q"):
                        address = "bcrt1q" + address[4:]
            
            elif address_type == 'nested-segwit':
                address = wallet.p2sh_p2wpkh_address()
            
            else:  # legacy
                address = wallet.p2pkh_address(testnet=is_testnet)
            
            # Validate the generated address format
            if network == "regtest":
                if address_type == 'segwit' and not address.startswith("bcrt1q"):
                    raise ValueError(f"Invalid regtest SegWit address format: {address}")
                elif address_type == 'taproot' and not address.startswith("bcrt1p"):
                    raise ValueError(f"Invalid regtest Taproot address format: {address}")
                elif address_type == 'nested-segwit' and not address.startswith("2"):
                    raise ValueError(f"Invalid regtest nested SegWit address format: {address}")
                elif address_type == 'legacy' and not address[0] in ['m', 'n']:
                    raise ValueError(f"Invalid regtest legacy address format: {address}")
            
            elif network == "testnet":
                if address_type == 'segwit' and not address.startswith("tb1q"):
                    raise ValueError(f"Invalid testnet SegWit address format: {address}")
                elif address_type == 'taproot' and not address.startswith("tb1p"):
                    raise ValueError(f"Invalid testnet Taproot address format: {address}")
                elif address_type == 'nested-segwit' and not address.startswith("2"):
                    raise ValueError(f"Invalid testnet nested SegWit address format: {address}")
                elif address_type == 'legacy' and not address[0] in ['m', 'n']:
                    raise ValueError(f"Invalid testnet legacy address format: {address}")
            
            elif network == "mainnet":
                if address_type == 'segwit' and not address.startswith("bc1q"):
                    raise ValueError(f"Invalid mainnet SegWit address format: {address}")
                elif address_type == 'taproot' and not address.startswith("bc1p"):
                    raise ValueError(f"Invalid mainnet Taproot address format: {address}")
                elif address_type == 'nested-segwit' and not address.startswith("3"):
                    raise ValueError(f"Invalid mainnet nested SegWit address format: {address}")
                elif address_type == 'legacy' and not address.startswith("1"):
                    raise ValueError(f"Invalid mainnet legacy address format: {address}")
            
            return address
        
        except Exception as e:
            logging.error(f"Error generating address: {str(e)}")
            raise ValueError(f"Failed to generate {address_type} address for {network} network: {str(e)}")
    
    def create_wallet(self, name: str, network: Optional[NetworkType] = None, 
                     address_count: int = 1, address_type: str = 'segwit') -> Dict:
        """Create a new HD wallet with encrypted storage and multiple initial addresses"""
        try:
            name = self._validate_wallet_name(name)
            if self._wallet_exists(name):
                raise ValueError(f"Wallet '{name}' already exists")
            
            # Validate network and address type
            network = network or self.network
            if network not in ["mainnet", "testnet", "regtest"]:
                raise ValueError(f"Invalid network type: {network}")
            
            if address_type not in ["legacy", "segwit", "nested-segwit", "taproot"]:
                raise ValueError(f"Invalid address type: {address_type}")
            
            # Generate mnemonic and create wallet
            mnemonic = generate_mnemonic(strength=256)
            wallet = HDWallet(symbol=BTC)
            wallet.from_mnemonic(mnemonic=mnemonic)
            
            # Generate initial addresses
            addresses = []
            for i in range(address_count):
                path = self._get_derivation_path(network, address_type, i)
                wallet.clean_derivation()
                wallet.from_path(path)
                address = self._get_address_for_type(wallet, network, address_type)
                addresses.append(address)
            
            # Prepare wallet data
            wallet_data = {
                "name": name,
                "network": network,
                "address_type": address_type,
                "encrypted_mnemonic": self.fernet.encrypt(mnemonic.encode()).decode(),
                "addresses": addresses,
                "address_index": address_count,
                "created_at": str(datetime.datetime.now())
            }
            
            # Save wallet
            self._save_wallet(name, wallet_data)
            
            # Display the created wallet with clear network information
            console.print(f"\n[bold green]✅ Created new wallet:[/bold green]")
            console.print(f"[cyan]Name:[/cyan] {name}")
            console.print(f"[magenta]Network:[/magenta] {network}")
            console.print(f"[yellow]Type:[/yellow] {address_type}")
            console.print("\n[bold]Generated Addresses:[/bold]")
            
            for i, addr in enumerate(addresses):
                console.print(f"[green]Address {i+1}:[/green] {addr}")
                console.print(f"[blue]Path:[/blue] {self._get_derivation_path(network, address_type, i)}")
            
            # Show network-specific instructions
            if network == "regtest":
                console.print("\n[bold yellow]Polar Usage Instructions:[/bold yellow]")
                console.print("1. Copy an address above")
                console.print(f"2. Verify it starts with the correct prefix for {network}:")
                console.print(f"   - SegWit: bcrt1q...")
                console.print(f"   - Taproot: bcrt1p...")
                console.print(f"   - Nested SegWit: 2...")
                console.print(f"   - Legacy: m... or n...")
                console.print("3. Open Polar and select your regtest network")
                console.print("4. Find a funded node and click 'Send Bitcoin'")
                console.print("5. Paste the address and specify amount")
                console.print("6. Click 'Send' and mine a new block")
            
            return wallet_data
            
        except Exception as e:
            logging.error(f"Error creating wallet: {str(e)}")
            raise
    
    def get_wallet(self, name: Any) -> Optional[Dict]:
        """Get wallet information with input validation"""
        try:
            validated_name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(validated_name)
            if wallet_data:
                display_wallet(wallet_data)
            return wallet_data
        except Exception as e:
            logging.error(f"Error loading wallet '{name}': {str(e)}")
            return None
    
    def list_wallets(self) -> None:
        """List all available wallets with their networks"""
        wallets = []
        for wallet_file in self.wallets_dir.glob("*.json"):
            try:
                wallet_data = self._load_wallet(wallet_file.stem)
                if wallet_data:
                    wallets.append({
                        "name": wallet_data["name"],
                        "network": wallet_data.get("network", "mainnet"),
                        "addresses": wallet_data["addresses"]
                    })
            except Exception as e:
                logging.error(f"Error loading wallet {wallet_file.stem}: {str(e)}")
        
        # Display wallets in a formatted table
        display_wallets(wallets)
    
    def generate_address(self, name: str, network: Optional[NetworkType] = None, 
                        address_type: Optional[str] = None) -> str:
        """Generate a new address for the wallet"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")
            
            network = network or wallet_data.get("network", "mainnet")
            address_type = address_type or wallet_data.get("address_type", "legacy")
            
            # Decrypt mnemonic and recreate wallet
            mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
            wallet = HDWallet(symbol=BTC)
            wallet.from_mnemonic(mnemonic=mnemonic)
            
            # Generate new address
            wallet.clean_derivation()
            path = self._get_derivation_path(network, address_type, wallet_data['address_index'])
            wallet.from_path(path)
            
            # Get appropriate address based on type and network
            address = self._get_address_for_type(wallet, network, address_type)
            
            # Update wallet data
            wallet_data["addresses"].append(address)
            wallet_data["address_index"] += 1
            self._save_wallet(name, wallet_data)
            
            # Display the new address
            console.print(f"\n[bold green]Generated new {address_type} address:[/bold green]")
            console.print(f"[yellow]Network:[/yellow] {network}")
            console.print(f"[yellow]Address:[/yellow] {address}")
            console.print(f"[yellow]Path:[/yellow] {path}\n")
            
            return address
        except Exception as e:
            logging.error(f"Error generating address for wallet '{name}': {str(e)}")
            raise
    
    def _wallet_exists(self, name: str) -> bool:
        """Check if wallet exists"""
        try:
            name = self._validate_wallet_name(name)
            return (self.wallets_dir / f"{name}.json").exists()
        except Exception:
            return False
    
    def _save_wallet(self, name: str, data: Dict) -> None:
        """Save wallet data to file"""
        try:
            name = self._validate_wallet_name(name)
            wallet_file = self.wallets_dir / f"{name}.json"
            with wallet_file.open('w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving wallet '{name}': {str(e)}")
            raise
    
    def _load_wallet(self, name: str) -> Optional[Dict]:
        """Load wallet data from file"""
        try:
            name = self._validate_wallet_name(name)
            wallet_file = self.wallets_dir / f"{name}.json"
            if not wallet_file.exists():
                raise FileNotFoundError(f"Wallet file for '{name}' not found")
            with wallet_file.open('r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading wallet '{name}': {str(e)}")
            return None
    
    def generate_addresses(self, name: str, count: int = 1, network: Optional[NetworkType] = None,
                          address_type: Optional[str] = None) -> List[str]:
        """Generate multiple new addresses for the wallet"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")
            
            network = network or wallet_data.get("network", "mainnet")
            address_type = address_type or wallet_data.get("address_type", "segwit")
            new_addresses = []
            
            # Decrypt mnemonic and recreate wallet
            mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
            wallet = HDWallet(symbol=BTC)
            wallet.from_mnemonic(mnemonic=mnemonic)
            
            # Generate new addresses
            current_index = wallet_data['address_index']
            for i in range(count):
                wallet.clean_derivation()
                path = self._get_derivation_path(network, address_type, current_index + i)
                wallet.from_path(path)
                
                # Get appropriate address based on type and network
                address = self._get_address_for_type(wallet, network, address_type)
                new_addresses.append(address)
            
            # Update wallet data
            wallet_data["addresses"].extend(new_addresses)
            wallet_data["address_index"] = current_index + count
            self._save_wallet(name, wallet_data)
            
            # Display the new addresses
            console.print("\n[bold green]Generated new addresses:[/bold green]")
            for i, addr in enumerate(new_addresses):
                console.print(f"[yellow]Address {current_index + i + 1}:[/yellow] {addr}")
                path = self._get_derivation_path(network, address_type, current_index + i)
                console.print(f"[blue]Path:[/blue] {path}")
            
            if network == "regtest":
                console.print("\n[bold yellow]Polar Usage Instructions:[/bold yellow]")
                console.print("1. Copy any address above (should start with 'bcrt1q' for SegWit)")
                console.print("2. Use in Polar to receive regtest bitcoin")
            
            return new_addresses
        except Exception as e:
            logging.error(f"Error generating addresses for wallet '{name}': {str(e)}")
            raise

    def get_network_info(self, name: str, network: Optional[NetworkType] = None, address_type: Optional[str] = None) -> None:
        """Display network-specific wallet information"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")
            
            if network:
                wallet_data['network'] = network
            
            display_network_addresses(wallet_data, address_type)
        except Exception as e:
            logging.error(f"Error displaying wallet info: {str(e)}")
            raise

def display_error(error: Union[str, Dict, Exception]) -> None:
    """Safely display error messages"""
    if isinstance(error, dict):
        message = error.get('error') or str(error)
    else:
        message = str(error)
    console.print(f"❌ Error: {message}")

# Create a global instance
wallet_manager = WalletManager() 