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
from bitcoinutils.setup import setup
from bitcoinutils.keys import PrivateKey, PublicKey
from bitcoinutils.script import Script
from bitcoinutils.transactions import Transaction as BitcoinTransaction, TxInput, TxOutput
import hashlib
import binascii
from .config import get_settings
import time
from decimal import Decimal
from bitcoinrpc.authproxy import AuthServiceProxy
from .schemas import UTXO, Transaction
import requests

settings = get_settings()
console = Console()

# Define network types
NetworkType = Literal["mainnet", "testnet", "regtest"]

def to_bytes(string: str) -> bytes:
    """Convert a hex string to bytes."""
    return bytes.fromhex(string)

def _init_network(network: NetworkType) -> None:
    """Initialize bitcoin-utils with the correct network"""
    if network == "mainnet":
        setup('mainnet')
    elif network in ["testnet", "regtest"]:  # Both testnet and regtest use testnet network
        setup('testnet')

def _get_address_from_private_key(private_key: PrivateKey, network: NetworkType, address_type: str) -> str:
    """Generate address from private key based on type"""
    public_key = private_key.get_public_key()
    
    if address_type == 'taproot':
        raise NotImplementedError("Taproot addresses are not supported in the current version")
    elif address_type == 'segwit':
        # P2WPKH (Native SegWit) address
        return public_key.get_segwit_address().to_string()
    elif address_type == 'nested-segwit':
        # P2SH-P2WPKH (Nested SegWit) address
        return public_key.get_segwit_address().to_string()
    else:
        # P2PKH (Legacy) address
        return public_key.get_address().to_string()

def _bech32_polymod(values):
    """Internal function that computes the Bech32 checksum."""
    generator = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk

def _bech32_hrp_expand(hrp):
    """Expand the HRP into values for checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def _bech32_verify_checksum(hrp, data):
    """Verify a checksum given HRP and converted data characters."""
    return _bech32_polymod(_bech32_hrp_expand(hrp) + data) == 1

def _bech32_create_checksum(hrp, data, spec='bech32m'):
    """Compute the checksum values given HRP and data."""
    values = _bech32_hrp_expand(hrp) + data
    const = 0x2bc830a3 if spec == 'bech32m' else 1
    polymod = _bech32_polymod(values + [0,0,0,0,0,0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]

def _bech32_encode(hrp, data, spec='bech32m'):
    """Compute a Bech32 string given HRP and data values."""
    CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    combined = data + _bech32_create_checksum(hrp, data, spec)
    return hrp + '1' + ''.join([CHARSET[d] for d in combined])

def _convert_bits(data, frombits, tobits, pad=True):
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret

def create_p2tr_address(pubkey_hex: str, network: NetworkType = "mainnet") -> str:
    """Create a P2TR (Taproot) address from a public key."""
    try:
        # Convert the hex public key to bytes and get x coordinate only
        pubkey_bytes = list(to_bytes(pubkey_hex[2:66]))  # x-coordinate only, convert to list of integers
        
        # Convert 32-byte pubkey to 5-bit array
        data = _convert_bits(pubkey_bytes, 8, 5)
        if data is None:
            raise ValueError("Failed to convert pubkey bits")
        
        # Add witness version (0x01 for Taproot)
        version_data = [0x01] + data
        
        # Get the correct HRP based on network
        if network == "mainnet":
            hrp = "bc"
        elif network == "testnet":
            hrp = "tb"
        else:  # regtest
            hrp = "bcrt"
        
        # Encode with bech32m
        return _bech32_encode(hrp, version_data, spec='bech32m')
    except Exception as e:
        raise ValueError(f"Failed to create P2TR address: {str(e)}")

def _get_address_for_type(self, wallet: HDWallet, network: NetworkType, address_type: str) -> str:
    """Generate address based on network and address type"""
    try:
        logging.info(f"Generating {address_type} address for network: {network}")
        
        # Set up network first
        if network in ["testnet", "regtest"]:
            logging.info("Setting up testnet/regtest configuration")
            setup('testnet')  # Both testnet and regtest use testnet settings
            wallet.cryptocurrency = BitcoinTestnet
            logging.info("Network setup complete: testnet")
            
            # Get private key and create WIF manually for testnet
            private_key_hex = wallet.private_key()
            logging.info("Creating private key for testnet/regtest")
            # Convert hex string to integer
            private_key_int = int(private_key_hex, 16)
            private_key = PrivateKey(secret_exponent=private_key_int)
            logging.info("Private key created successfully")
        else:
            logging.info("Setting up mainnet configuration")
            setup('mainnet')
            wallet.cryptocurrency = BitcoinMainnet
            logging.info("Network setup complete: mainnet")
            
            # Get private key and create WIF manually for mainnet
            private_key_hex = wallet.private_key()
            logging.info("Creating private key for mainnet")
            # Convert hex string to integer
            private_key_int = int(private_key_hex, 16)
            private_key = PrivateKey(secret_exponent=private_key_int)
            logging.info("Private key created successfully")
        
        # Generate address based on type
        logging.info("Getting PublicKey")
        public_key = private_key.get_public_key()
        logging.info("PublicKey obtained successfully")
        
        if address_type == 'taproot':
            logging.info("Generating Taproot address")
            pubkey_hex = public_key.to_hex()
            address = create_p2tr_address(pubkey_hex, network)
            logging.info(f"Taproot address generated: {address}")
        elif address_type == 'segwit':
            logging.info("Generating SegWit address")
            address = public_key.get_segwit_address().to_string()
            logging.info(f"SegWit address generated: {address}")
        elif address_type == 'nested-segwit':
            logging.info("Generating Nested SegWit address")
            address = public_key.get_segwit_address().to_string()
            logging.info(f"Nested SegWit address generated: {address}")
        else:
            logging.info("Generating Legacy address")
            address = public_key.get_address().to_string()
            logging.info(f"Legacy address generated: {address}")
        
        # Convert address prefix for regtest if needed
        if network == "regtest":
            logging.info("Converting address for regtest network")
            original_address = address
            if address_type == 'segwit' and address.startswith("tb1q"):
                address = "bcrt1q" + address[4:]
                logging.info(f"Converted SegWit address from {original_address} to {address}")
            elif address_type == 'taproot' and address.startswith("tb1p"):
                address = "bcrt1p" + address[4:]
                logging.info(f"Converted Taproot address from {original_address} to {address}")
            elif address_type == 'nested-segwit' and not address.startswith("2"):
                logging.error(f"Invalid regtest nested SegWit address format: {address}")
                raise ValueError(f"Invalid regtest nested SegWit address format: {address}")
            elif address_type == 'legacy' and not address[0] in ['m', 'n']:
                logging.error(f"Invalid regtest legacy address format: {address}")
                raise ValueError(f"Invalid regtest legacy address format: {address}")
        
        logging.info(f"Final address generated successfully: {address}")
        return address
    
    except Exception as e:
        logging.error(f"Error generating address: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to generate {address_type} address for {network} network: {str(e)}")

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

class WalletManager:
    """Manages HD wallets with local key storage and encryption"""
    
    def __init__(self):
        self.wallets_dir = Path("data/wallets")
        self.wallets_dir.mkdir(parents=True, exist_ok=True)
        self._init_encryption()
        self.network = getattr(settings, "bitcoin_network", "mainnet")
        self.default_ports = {
            "regtest": 18443,
            "testnet": 18332,
            "mainnet": 8332
        }
        # Initialize database
        from .database import Database
        self.database = Database()
        
        # Initialize bitcoin-utils with default network
        if self.network in ["testnet", "regtest"]:
            setup('testnet')
        else:
            setup('mainnet')
    
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
            logging.info(f"Generating {address_type} address for network: {network}")
            
            # Set up network first
            if network in ["testnet", "regtest"]:
                logging.info("Setting up testnet/regtest configuration")
                setup('testnet')  # Both testnet and regtest use testnet settings
                wallet.cryptocurrency = BitcoinTestnet
                logging.info("Network setup complete: testnet")
                
                # Get private key and create WIF manually for testnet
                private_key_hex = wallet.private_key()
                logging.info("Creating private key for testnet/regtest")
                # Convert hex string to integer
                private_key_int = int(private_key_hex, 16)
                private_key = PrivateKey(secret_exponent=private_key_int)
                logging.info("Private key created successfully")
            else:
                logging.info("Setting up mainnet configuration")
                setup('mainnet')
                wallet.cryptocurrency = BitcoinMainnet
                logging.info("Network setup complete: mainnet")
                
                # Get private key and create WIF manually for mainnet
                private_key_hex = wallet.private_key()
                logging.info("Creating private key for mainnet")
                # Convert hex string to integer
                private_key_int = int(private_key_hex, 16)
                private_key = PrivateKey(secret_exponent=private_key_int)
                logging.info("Private key created successfully")
            
            # Generate address based on type
            logging.info("Getting PublicKey")
            public_key = private_key.get_public_key()
            logging.info("PublicKey obtained successfully")
            
            if address_type == 'taproot':
                logging.info("Generating Taproot address")
                pubkey_hex = public_key.to_hex()
                address = create_p2tr_address(pubkey_hex, network)
                logging.info(f"Taproot address generated: {address}")
            elif address_type == 'segwit':
                logging.info("Generating SegWit address")
                address = public_key.get_segwit_address().to_string()
                logging.info(f"SegWit address generated: {address}")
            elif address_type == 'nested-segwit':
                logging.info("Generating Nested SegWit address")
                address = public_key.get_segwit_address().to_string()
                logging.info(f"Nested SegWit address generated: {address}")
            else:
                logging.info("Generating Legacy address")
                address = public_key.get_address().to_string()
                logging.info(f"Legacy address generated: {address}")
            
            # Convert address prefix for regtest if needed
            if network == "regtest":
                logging.info("Converting address for regtest network")
                original_address = address
                if address_type == 'segwit' and address.startswith("tb1q"):
                    address = "bcrt1q" + address[4:]
                    logging.info(f"Converted SegWit address from {original_address} to {address}")
                elif address_type == 'taproot' and address.startswith("tb1p"):
                    address = "bcrt1p" + address[4:]
                    logging.info(f"Converted Taproot address from {original_address} to {address}")
                elif address_type == 'nested-segwit' and not address.startswith("2"):
                    logging.error(f"Invalid regtest nested SegWit address format: {address}")
                    raise ValueError(f"Invalid regtest nested SegWit address format: {address}")
                elif address_type == 'legacy' and not address[0] in ['m', 'n']:
                    logging.error(f"Invalid regtest legacy address format: {address}")
                    raise ValueError(f"Invalid regtest legacy address format: {address}")
            
            logging.info(f"Final address generated successfully: {address}")
            return address
        
        except Exception as e:
            logging.error(f"Error generating address: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to generate {address_type} address for {network} network: {str(e)}")
    
    def create_wallet(self, name: str, network: Optional[NetworkType] = None, 
                     address_count: int = 1, address_type: str = 'segwit') -> Dict:
        """Create a new HD wallet with encrypted storage and multiple initial addresses"""
        try:
            logging.info(f"Creating new wallet: {name} (network: {network}, type: {address_type})")
            
            name = self._validate_wallet_name(name)
            if self._wallet_exists(name):
                logging.error(f"Wallet '{name}' already exists")
                raise ValueError(f"Wallet '{name}' already exists")
            
            # Validate network and address type
            network = network or self.network
            if network not in ["mainnet", "testnet", "regtest"]:
                logging.error(f"Invalid network type: {network}")
                raise ValueError(f"Invalid network type: {network}")
            
            if address_type not in ["legacy", "segwit", "nested-segwit", "taproot"]:
                logging.error(f"Invalid address type: {address_type}")
                raise ValueError(f"Invalid address type: {address_type}")
            
            # Set up network first
            if network in ["testnet", "regtest"]:
                logging.info("Setting up testnet/regtest configuration")
                setup('testnet')  # Both testnet and regtest use testnet settings
                logging.info("Network setup complete: testnet")
            else:
                logging.info("Setting up mainnet configuration")
                setup('mainnet')
                logging.info("Network setup complete: mainnet")
            
            # Generate mnemonic and create wallet
            logging.info("Generating mnemonic")
            mnemonic = generate_mnemonic(strength=256)
            logging.info("Creating HDWallet instance")
            wallet = HDWallet(symbol=BTC)
            
            # Set the correct network for HDWallet
            if network in ["testnet", "regtest"]:
                wallet.cryptocurrency = BitcoinTestnet
            else:
                wallet.cryptocurrency = BitcoinMainnet
            
            # Initialize the wallet with mnemonic
            logging.info("Initializing wallet with mnemonic")
            wallet.from_mnemonic(mnemonic=mnemonic)
            logging.info("Wallet initialized successfully")
            
            # Generate initial addresses
            addresses = []
            for i in range(address_count):
                logging.info(f"Generating address {i+1} of {address_count}")
                path = self._get_derivation_path(network, address_type, i)
                logging.info(f"Using derivation path: {path}")
                wallet.clean_derivation()
                wallet.from_path(path)
                address = self._get_address_for_type(wallet, network, address_type)
                addresses.append(address)
                logging.info(f"Address {i+1} generated: {address}")
            
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
            logging.info("Saving wallet data")
            self._save_wallet(name, wallet_data)
            logging.info("Wallet saved successfully")
            
            # Display the created wallet with clear network information
            console.print(f"\n[bold green]✅ Created new wallet:[/bold green]")
            console.print(f"[cyan]Name:[/cyan] {name}")
            console.print(f"[magenta]Network:[/magenta] {network}")
            console.print(f"[yellow]Type:[/yellow] {address_type}")
            console.print("\n[bold]Generated Addresses:[/bold]")
            
            for i, addr in enumerate(addresses):
                console.print(f"[green]Address {i+1}:[/green] {addr}")
                console.print(f"[blue]Path:[/blue] {self._get_derivation_path(network, address_type, i)}")
            
            return wallet_data
            
        except Exception as e:
            logging.error(f"Error creating wallet: {str(e)}", exc_info=True)
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
            address_type = address_type or wallet_data.get("address_type", "segwit")
            
            # Initialize network
            _init_network(network)
            
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

    def _decode_bech32m(self, addr: str) -> Optional[str]:
        """Decode a bech32m address and return the public key in hex format"""
        try:
            hrp = "bcrt" if addr.startswith("bcrt1") else "bc" if addr.startswith("bc1") else "tb"
            if not addr.startswith(f"{hrp}1p"):
                return None
            
            # Remove the hrp and separator
            data = addr[len(hrp) + 2:]
            
            # Convert from bech32m to bytes
            CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
            data = [CHARSET.find(c) for c in data]
            if -1 in data:
                return None
            
            # Convert 5-bit array to bytes
            acc = 0
            bits = 0
            result = []
            for value in data[:-6]:  # Exclude checksum
                acc = (acc << 5) | value
                bits += 5
                while bits >= 8:
                    bits -= 8
                    result.append((acc >> bits) & 0xFF)
            
            # Skip version byte (first byte should be 1 for Taproot)
            if len(result) < 33 or result[0] != 1:
                return None
            
            # Return the 32-byte public key in hex format
            return ''.join(f'{b:02x}' for b in result[1:33])
        except Exception as e:
            logging.error(f"Error decoding bech32m address: {str(e)}")
            return None

    def _get_taproot_pubkey(self, address: str) -> Optional[str]:
        """Extract public key from a Taproot address"""
        try:
            from bech32 import decode, convertbits
            
            # Decode the bech32m address
            if address.startswith('bcrt1'):
                hrp = 'bcrt'
            elif address.startswith('tb1'):
                hrp = 'tb'
            elif address.startswith('bc1'):
                hrp = 'bc'
            else:
                return None
            
            decoded = decode(hrp, address)
            if decoded is None or len(decoded) != 2:
                return None
            
            version, data = decoded
            
            # Convert from 5-bit to 8-bit
            decoded_data = convertbits(data, 5, 8, False)
            if decoded_data is None or len(decoded_data) != 32:
                return None
            
            # Convert to hex
            return ''.join(f'{x:02x}' for x in decoded_data)
        except Exception as e:
            logging.error(f"Error extracting Taproot public key: {str(e)}")
            return None

    def get_balance(self, name: str) -> Dict[str, float]:
        """Get the balance for a wallet"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")

            network = wallet_data.get("network", "mainnet")
            addresses = wallet_data["addresses"]
            
            # Get RPC configuration from environment variables
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            
            # Set RPC port based on network, but allow override from env
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            from bitcoinrpc.authproxy import AuthServiceProxy
            from bitcoinutils.script import Script
            
            # Create RPC connection
            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )

            total_balance = 0
            balances = {}

            # Get balance for each address using scantxoutset and sync UTXOs
            for address in addresses:
                try:
                    addr_type = get_address_type(address)
                    logging.info(f"Processing {addr_type} address: {address}")

                    # Create the appropriate descriptor based on address type and network
                    if network == "regtest":
                        if addr_type == 'taproot':
                            if address.startswith("bcrt1p"):
                                desc = f"addr({address})"
                            else:
                                logging.error(f"Invalid regtest Taproot address format: {address}")
                                continue
                        elif addr_type == 'segwit':
                            if address.startswith("bcrt1q"):
                                desc = f"addr({address})"
                            else:
                                logging.error(f"Invalid regtest SegWit address format: {address}")
                                continue
                        elif addr_type == 'nested-segwit':
                            if address.startswith("2"):
                                desc = f"addr({address})"
                            else:
                                logging.error(f"Invalid regtest nested SegWit address format: {address}")
                                continue
                        else:  # legacy
                            if address.startswith(("m", "n")):
                                desc = f"addr({address})"
                            else:
                                logging.error(f"Invalid regtest legacy address format: {address}")
                                continue
                    else:
                        desc = f"addr({address})"

                    logging.info(f"Using descriptor: {desc}")

                    # Scan the UTXO set for this address
                    scan_result = rpc_connection.scantxoutset("start", [desc])
                    
                    if scan_result["success"]:
                        confirmed_balance = float(scan_result["total_amount"]) if "total_amount" in scan_result else 0
                        
                        # Store UTXOs in database
                        if "unspents" in scan_result:
                            for utxo in scan_result["unspents"]:
                                utxo_obj = UTXO(
                                    txid=utxo["txid"],
                                    vout=utxo["vout"],
                                    amount=Decimal(str(utxo["amount"])),
                                    address=address,
                                    frozen=False,
                                    wallet_name=name
                                )
                                self.database.store_utxo(utxo_obj)
                                logging.info(f"Stored UTXO: {utxo['txid']}:{utxo['vout']}")
                        
                        balances[address] = {
                            "confirmed": confirmed_balance,
                            "unconfirmed": 0,  # scantxoutset only shows confirmed balance
                            "total": confirmed_balance,
                            "type": addr_type
                        }
                        
                        total_balance += confirmed_balance
                        logging.info(f"Successfully retrieved balance for {addr_type} address {address}")
                    else:
                        logging.error(f"Scan failed for address {address}")
                        balances[address] = {
                            "error": "Scan failed",
                            "type": addr_type
                        }
                    
                except Exception as e:
                    logging.error(f"Error processing address {address}: {str(e)}")
                    balances[address] = {
                        "error": str(e),
                        "type": get_address_type(address)
                    }

            # Update wallet balance
            self.database.update_wallet_balance(name, Decimal(str(total_balance)))

            # Display the balances with improved formatting
            console.print(f"\n[bold green]Wallet Balance - {name}[/bold green]")
            console.print(f"[magenta]Network:[/magenta] {network}")
            console.print(f"[yellow]Total Confirmed Balance:[/yellow] {total_balance} BTC")
            console.print("\n[bold]Address Balances:[/bold]")
            
            for addr, balance in balances.items():
                if "error" in balance:
                    console.print(f"[red]Address {addr} ({balance.get('type', 'unknown')}):[/red]")
                    console.print(f"  Error: {balance['error']}")
                else:
                    addr_type = balance.get('type', 'unknown')
                    console.print(f"[green]Address[/green] ({addr_type}): {addr}")
                    console.print(f"  Confirmed: {balance['confirmed']} BTC")
                    console.print("")

            return {
                "total_confirmed": total_balance,
                "total_unconfirmed": 0,  # scantxoutset only shows confirmed balance
                "address_balances": balances
            }

        except Exception as e:
            logging.error(f"Error getting balance for wallet '{name}': {str(e)}")
            raise

    def _calculate_sighash(self, tx: BitcoinTransaction, input_index: int, script: Script) -> bytes:
        """Calculate the signature hash for a transaction input"""
        try:
            # Create a copy of the transaction
            tx_copy = BitcoinTransaction(tx.inputs[:], tx.outputs[:])
            
            # Clear all input scripts
            for i in range(len(tx_copy.inputs)):
                tx_copy.inputs[i].script_sig = Script([])
            
            # Set the script of the input being signed
            if isinstance(script, str):
                # If it's a hex string, use it directly
                if all(c in '0123456789abcdefABCDEF' for c in script):
                    script_hex = script
                else:
                    script_hex = script.encode('utf-8').hex()
            elif isinstance(script, bytes):
                script_hex = script.hex()
            elif isinstance(script, Script):
                # For Script objects, use the script directly
                tx_copy.inputs[input_index].script_sig = script
                
                # Serialize the transaction
                ser_tx = tx_copy.serialize()
                
                # Add SIGHASH_ALL
                ser_tx += bytes([0x01, 0x00, 0x00, 0x00])
                
                # Double SHA256
                return hashlib.sha256(hashlib.sha256(ser_tx).digest()).digest()
            else:
                raise ValueError(f"Invalid script type: {type(script)}")
            
            # Create script from hex (for str and bytes cases)
            tx_copy.inputs[input_index].script_sig = Script.from_hex(script_hex)
            
            # Serialize the transaction
            ser_tx = tx_copy.serialize()
            
            # Add SIGHASH_ALL
            ser_tx += bytes([0x01, 0x00, 0x00, 0x00])
            
            # Double SHA256
            return hashlib.sha256(hashlib.sha256(ser_tx).digest()).digest()
            
        except Exception as e:
            logging.error(f"Error calculating sighash: {str(e)}")
            raise ValueError(f"Failed to calculate sighash: {str(e)}")

    def _create_output_script(self, address: str) -> Script:
        """Create output script from address"""
        from bitcoinutils.keys import P2pkhAddress, P2shAddress, P2wpkhAddress, P2wshAddress
        from bitcoinutils.constants import SIGHASH_ALL
        
        try:
            if address.startswith(('bc1q', 'tb1q', 'bcrt1q')):  # Native SegWit
                # Create P2WPKH script
                segwit_addr = P2wpkhAddress(address)
                return segwit_addr.to_script_pub_key()
            elif address.startswith(('bc1p', 'tb1p', 'bcrt1p')):  # Taproot
                # For Taproot, we'll use a simple witness program
                return Script(['OP_1', address[4:]])
            elif address.startswith(('2', '3')):  # P2SH
                # Create P2SH script
                p2sh_addr = P2shAddress(address)
                return p2sh_addr.to_script_pub_key()
            else:  # Legacy
                # Create P2PKH script
                p2pkh_addr = P2pkhAddress(address)
                return p2pkh_addr.to_script_pub_key()
        except Exception as e:
            logging.error(f"Error creating output script for address {address}: {str(e)}")
            raise ValueError(f"Failed to create output script: {str(e)}")

    def _create_input_script(self, private_key: PrivateKey, public_key: PublicKey, sighash: bytes) -> Script:
        """Create input script (scriptSig) for transaction signing"""
        try:
            # Sign the hash
            signature = private_key.sign(sighash) + b'\x01'  # Add SIGHASH_ALL
            
            # Create P2PKH script sig
            return Script([signature.hex(), public_key.to_hex()])
        except Exception as e:
            logging.error(f"Error creating input script: {str(e)}")
            raise ValueError(f"Failed to create input script: {str(e)}")

    def send_bitcoin(self, name: str, to_address: str, amount: Decimal, 
                    memo: Optional[str] = None, fee_rate: Optional[float] = None) -> str:
        """Send bitcoin to an address with optional memo"""
        try:
            logging.info(f"Starting send_bitcoin for wallet: {name}")
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")

            network = wallet_data.get("network", "mainnet")
            logging.info(f"Network: {network}")
            
            # Get RPC configuration
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))
            logging.info(f"RPC connection details - Host: {rpc_host}, Port: {rpc_port}")

            # Create RPC connection
            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )
            logging.info("RPC connection established")

            # Get available UTXOs
            utxos = self.database.get_utxos(name, include_frozen=False)
            if not utxos:
                raise ValueError("No available UTXOs found")
            logging.info(f"Found {len(utxos)} available UTXOs")

            total_available = sum(utxo.amount for utxo in utxos)
            if total_available < amount:
                raise ValueError(f"Insufficient funds. Available: {total_available}, Required: {amount}")
            logging.info(f"Total available: {total_available}, Amount to send: {amount}")

            # Generate a change address
            change_address = self.generate_address(name)
            logging.info(f"Generated change address: {change_address}")

            # Create raw inputs
            inputs = []
            input_amount = Decimal('0')
            input_addresses = []

            # Add inputs until we have enough funds
            for utxo in utxos:
                if input_amount >= amount:
                    break
                
                inputs.append({
                    "txid": utxo.txid,
                    "vout": utxo.vout
                })
                input_amount += utxo.amount
                input_addresses.append(utxo.address)
                logging.info(f"Added input - TXID: {utxo.txid}, Vout: {utxo.vout}, Amount: {utxo.amount}")

            # Create outputs
            outputs = {}
            
            # Payment output - convert Decimal to float with 8 decimal places
            outputs[to_address] = round(float(amount), 8)
            logging.info(f"Added payment output - Address: {to_address}, Amount: {amount}")
            
            # Add memo output if provided
            if memo:
                memo_bytes = memo.encode('utf-8').hex()
                outputs["data"] = memo_bytes
                logging.info(f"Added memo output - Memo: {memo}")

            # Add change output if needed
            # Calculate fee in satoshis per byte
            fee_rate = fee_rate if fee_rate else 5.0  # Default to 5 sat/vB
            
            # Estimate transaction size in bytes
            estimated_size = (len(inputs) * 180) + (len(outputs) * 34) + 10  # rough estimation
            
            # Calculate fee in BTC: (size * sat/vB) / 100000000
            fee = Decimal(str(estimated_size * fee_rate)) / Decimal('100000000')
            logging.info(f"Fee calculation - Rate: {fee_rate} sat/vB, Size: {estimated_size} bytes, Fee: {fee} BTC")
            
            change_amount = input_amount - amount - fee
            if change_amount > Decimal('0.00001'):  # Only add change if it's significant
                outputs[change_address] = round(float(change_amount), 8)
                logging.info(f"Added change output - Address: {change_address}, Amount: {change_amount}")

            # Create raw transaction
            logging.info("Creating raw transaction")
            raw_tx = rpc_connection.createrawtransaction(inputs, outputs)
            logging.info(f"Raw transaction created: {raw_tx}")

            # Get private keys for signing
            private_keys = []
            for addr in input_addresses:
                logging.info(f"Getting private key for address: {addr}")
                # Find the path for this address
                path = None
                for i, wallet_addr in enumerate(wallet_data["addresses"]):
                    if addr == wallet_addr:
                        path = self._get_derivation_path(network, wallet_data.get("address_type", "legacy"), i)
                        logging.info(f"Found path for address {addr}: {path}")
                        break

                if not path:
                    logging.warning(f"No path found for address {addr}")
                    continue

                # Get private key
                logging.info("Decrypting mnemonic")
                mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
                hd_wallet = HDWallet(symbol=BTC)
                hd_wallet.from_mnemonic(mnemonic=mnemonic)
                hd_wallet.clean_derivation()
                hd_wallet.from_path(path)
                private_key_hex = hd_wallet.private_key()
                private_key = PrivateKey(secret_exponent=int(private_key_hex, 16))
                wif = private_key.to_wif()
                private_keys.append(wif)
                logging.info(f"Added private key for address {addr}")

            # Sign raw transaction
            logging.info("Signing transaction")
            signed_tx = rpc_connection.signrawtransactionwithkey(raw_tx, private_keys)
            if not signed_tx["complete"]:
                raise ValueError("Failed to sign transaction completely")
            logging.info("Transaction signed successfully")

            # Send raw transaction
            logging.info("Broadcasting transaction")
            txid = rpc_connection.sendrawtransaction(signed_tx["hex"])
            logging.info(f"Transaction broadcast successfully, TXID: {txid}")

            # Store transaction in database
            tx_obj = Transaction(
                txid=txid,
                timestamp=int(time.time()),
                amount=amount,
                fee=fee,
                memo=memo,
                from_addresses=input_addresses,
                to_addresses=[to_address],
                wallet_name=name,
                change_address=change_address,
                status="pending"
            )
            self.database.store_transaction(tx_obj)
            logging.info("Transaction stored in database")

            # Update UTXO tracking
            for utxo in utxos[:len(inputs)]:
                self.database.remove_utxo(utxo.txid, utxo.vout)
                logging.info(f"Removed spent UTXO: {utxo.txid}:{utxo.vout}")

            console.print(f"\n[green]Transaction sent successfully![/green]")
            console.print(f"[yellow]TXID:[/yellow] {txid}")
            console.print(f"[yellow]Amount:[/yellow] {amount} BTC")
            console.print(f"[yellow]Fee:[/yellow] {fee} BTC")
            if memo:
                console.print(f"[yellow]Memo:[/yellow] {memo}")

            return txid

        except Exception as e:
            logging.error(f"Error sending bitcoin: {str(e)}", exc_info=True)
            raise

    def create_and_freeze_utxo(self, name: str, amount: Decimal, memo: Optional[str] = None) -> str:
        """Create a UTXO with specific value and freeze it"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")

            # Generate a new address for the UTXO
            address = self.generate_address(name)

            # Send bitcoin to the new address
            txid = self.send_bitcoin(name, address, amount, memo=memo)

            # Wait for one confirmation
            self._wait_for_confirmation(txid)

            # Get the output index (vout) for the new UTXO
            network = wallet_data.get("network", "mainnet")
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )

            tx = rpc_connection.getrawtransaction(txid, True)
            vout = None
            for i, output in enumerate(tx["vout"]):
                if output["scriptPubKey"]["addresses"][0] == address:
                    vout = i
                    break

            if vout is None:
                raise ValueError("Could not find the output in transaction")

            # Create and store the frozen UTXO
            utxo = UTXO(
                txid=txid,
                vout=vout,
                amount=amount,
                address=address,
                frozen=True,
                memo=memo,
                wallet_name=name
            )
            self.database.store_utxo(utxo)

            console.print(f"\n[green]Created and froze UTXO successfully![/green]")
            console.print(f"[yellow]TXID:[/yellow] {txid}")
            console.print(f"[yellow]Vout:[/yellow] {vout}")
            console.print(f"[yellow]Amount:[/yellow] {amount} BTC")
            console.print(f"[yellow]Address:[/yellow] {address}")
            if memo:
                console.print(f"[yellow]Memo:[/yellow] {memo}")

            return txid

        except Exception as e:
            logging.error(f"Error creating frozen UTXO: {str(e)}")
            raise

    def _wait_for_confirmation(self, txid: str, confirmations: int = 1):
        """Wait for a transaction to get the required number of confirmations"""
        try:
            network = self.network
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )

            while True:
                try:
                    tx = rpc_connection.getrawtransaction(txid, True)
                    if "confirmations" in tx and tx["confirmations"] >= confirmations:
                        break
                except Exception:
                    pass
                time.sleep(1)  # Wait for 1 second before checking again

        except Exception as e:
            logging.error(f"Error waiting for confirmation: {str(e)}")
            raise

# Create a global instance
wallet_manager = WalletManager() 