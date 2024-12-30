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
from . import WALLETS_DIR, BASE_DATA_DIR

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
        self.wallets_dir = WALLETS_DIR
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
        try:
            key_file = BASE_DATA_DIR / "wallet.key"
            if not key_file.exists():
                # Create directory if it doesn't exist
                key_file.parent.mkdir(parents=True, exist_ok=True)
                # Generate and save new key
                key = Fernet.generate_key()
                key_file.write_bytes(key)
                logging.info("Generated new encryption key")
            
            # Read the key and initialize Fernet
            key = key_file.read_bytes()
            self.fernet = Fernet(key)
            
            # Verify key is valid
            try:
                # Test encryption/decryption
                test_data = b"test"
                encrypted = self.fernet.encrypt(test_data)
                decrypted = self.fernet.decrypt(encrypted)
                if decrypted != test_data:
                    raise ValueError("Encryption key verification failed")
            except Exception as e:
                logging.error(f"Encryption key verification failed: {str(e)}")
                # Backup old key if it exists
                if key_file.exists():
                    backup_file = key_file.with_suffix('.key.backup')
                    key_file.rename(backup_file)
                    logging.info(f"Backed up old key to {backup_file}")
                
                # Generate new key
                key = Fernet.generate_key()
                key_file.write_bytes(key)
                self.fernet = Fernet(key)
                logging.info("Generated new encryption key after verification failure")
                
                console.print("[yellow]Warning: Encryption key was reset. You may need to recreate your wallets.[/yellow]")
                
        except Exception as e:
            logging.error(f"Error initializing encryption: {str(e)}")
            raise ValueError(f"Failed to initialize wallet encryption: {str(e)}")
    
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
    
    def get_wallet(self, name: str, suppress_output: bool = False) -> Optional[Dict]:
        """Get wallet information including the mnemonic if available."""
        try:
            name = self._validate_wallet_name(name)
            wallet_path = WALLETS_DIR / f"{name}.json"
            if not wallet_path.exists():
                if not suppress_output:
                    print(f"Wallet '{name}' not found")
                return None
                
            try:
                with open(wallet_path, 'r') as f:
                    wallet = json.load(f)
                    
                # Add mnemonic if available (encrypted)
                if 'encrypted_mnemonic' in wallet:
                    try:
                        mnemonic = self.fernet.decrypt(wallet['encrypted_mnemonic'].encode()).decode()
                        wallet['mnemonic'] = mnemonic
                    except Exception as e:
                        logging.error(f"Error decrypting mnemonic: {str(e)}")
                        # Don't include mnemonic if decryption fails
                        pass
                    
                return wallet
            except Exception as e:
                if not suppress_output:
                    print(f"Error reading wallet '{name}': {e}")
                return None
                
        except Exception as e:
            logging.error(f"Error getting wallet: {str(e)}")
            if not suppress_output:
                print(f"Error loading wallet: {str(e)}")
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
                        address_type: Optional[str] = None, quiet: bool = False) -> str:
        """Generate a new address for the wallet"""
        try:
            logging.info(f"Generating new address for wallet: {name}")
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")
            
            network = network or wallet_data.get("network", "mainnet")
            address_type = address_type or wallet_data.get("address_type", "segwit")
            current_index = wallet_data.get('address_index', 0)
            
            logging.info(f"Current wallet state - Network: {network}, Type: {address_type}, Index: {current_index}")
            
            # Initialize network
            _init_network(network)
            
            # Decrypt mnemonic and recreate wallet
            mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
            wallet = HDWallet(symbol=BTC)
            wallet.from_mnemonic(mnemonic=mnemonic)
            
            # Generate new address
            wallet.clean_derivation()
            path = self._get_derivation_path(network, address_type, current_index + 1)
            wallet.from_path(path)
            
            # Get appropriate address based on type and network
            address = self._get_address_for_type(wallet, network, address_type)
            logging.info(f"Generated new address: {address} at index {current_index + 1}")
            
            # Update wallet data
            wallet_data["addresses"].append(address)
            wallet_data["address_index"] = current_index + 1
            self._save_wallet(name, wallet_data)
            logging.info(f"Updated wallet data with new address")
            
            # Only display if not in quiet mode
            if not quiet:
                console.print(f"\nGenerated new {address_type} address:")
                console.print(f"Network: {network}")
                console.print(f"Address: {address}")
                console.print(f"Path: {path}\n")
            
            return address
        except Exception as e:
            logging.error(f"Error generating address for wallet '{name}': {str(e)}", exc_info=True)
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
            try:
                mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
            except Exception as e:
                raise ValueError(f"Failed to decrypt wallet mnemonic: {str(e)}")

            wallet = HDWallet(symbol=BTC)
            wallet.from_mnemonic(mnemonic=mnemonic)
            
            # Generate new addresses
            current_index = wallet_data.get('address_index', 0)  # Default to 0 if not found
            for i in range(count):
                try:
                    wallet.clean_derivation()
                    path = self._get_derivation_path(network, address_type, current_index + i)
                    wallet.from_path(path)
                    
                    # Get appropriate address based on type and network
                    address = self._get_address_for_type(wallet, network, address_type)
                    new_addresses.append(address)
                except Exception as e:
                    raise ValueError(f"Failed to generate address {i+1}: {str(e)}")
            
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
            raise ValueError(str(e))

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

    def get_balance(self, name: str, suppress_output: bool = False) -> Dict[str, float]:
        """Get the balance for a wallet and refresh UTXO information"""
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
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            # Create RPC connection
            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )

            total_balance = 0
            balances = {}
            
            # Get existing UTXOs and separate frozen from unfrozen
            existing_utxos = self.database.get_utxos(name, include_frozen=True)
            frozen_utxos = {(utxo.txid, utxo.vout): utxo for utxo in existing_utxos if utxo.frozen}
            unfrozen_utxos = {(utxo.txid, utxo.vout): utxo for utxo in existing_utxos if not utxo.frozen}
            
            # Clear only unfrozen UTXOs
            for utxo in unfrozen_utxos.values():
                self.database.remove_utxo(utxo.txid, utxo.vout)
            
            # Get required coinbase maturity
            required_depth = 100  # Both regtest and mainnet require 100 blocks

            # Get balance for each address using scantxoutset and sync UTXOs
            for address in addresses:
                try:
                    addr_type = get_address_type(address)
                    logging.info(f"Processing {addr_type} address: {address}")
                    
                    # Get descriptor based on address type
                    desc = None
                    if addr_type == "legacy":
                        desc = f"addr({address})"
                    elif addr_type == "p2sh-segwit":
                        desc = f"addr({address})"
                    elif addr_type == "segwit":
                        desc = f"addr({address})"
                    elif addr_type == "taproot":
                        desc = f"addr({address})"
                    else:
                        raise ValueError(f"Unsupported address type: {addr_type}")
                    
                    logging.info(f"Using descriptor: {desc}")

                    # Scan the UTXO set for this address
                    scan_result = rpc_connection.scantxoutset("start", [desc])
                    
                    if scan_result["success"]:
                        confirmed_balance = float(scan_result["total_amount"]) if "total_amount" in scan_result else 0
                        
                        # Store and verify UTXOs in database
                        if "unspents" in scan_result:
                            for utxo in scan_result["unspents"]:
                                try:
                                    # Get full transaction details
                                    tx = rpc_connection.getrawtransaction(utxo["txid"], True)
                                    
                                    # Check if it's a coinbase transaction
                                    is_coinbase = any(vin.get("coinbase") for vin in tx.get("vin", []))
                                    confirmations = tx.get("confirmations", 0)
                                    
                                    # Only store mature UTXOs
                                    if not is_coinbase or (is_coinbase and confirmations >= required_depth):
                                        # Check if this UTXO was frozen
                                        utxo_key = (utxo["txid"], utxo["vout"])
                                        frozen_utxo = frozen_utxos.get(utxo_key)
                                        
                                        utxo_obj = UTXO(
                                            txid=utxo["txid"],
                                            vout=utxo["vout"],
                                            amount=Decimal(str(utxo["amount"])),
                                            address=address,
                                            frozen=bool(frozen_utxo.frozen if frozen_utxo else False),
                                            memo=frozen_utxo.memo if frozen_utxo else None,
                                            wallet_name=name,
                                            confirmations=confirmations,
                                            is_coinbase=is_coinbase
                                        )
                                        self.database.store_utxo(utxo_obj)
                                        logging.info(f"Stored verified UTXO: {utxo['txid']}:{utxo['vout']}")
                                    else:
                                        logging.info(f"Skipping immature coinbase UTXO: {utxo['txid']}:{utxo['vout']}")
                                        confirmed_balance -= float(utxo["amount"])
                                except Exception as e:
                                    logging.error(f"Error verifying UTXO {utxo['txid']}: {str(e)}")
                                    continue
                    
                    balances[address] = {
                        "confirmed": confirmed_balance,
                        "unconfirmed": 0,  # scantxoutset only shows confirmed balance
                        "total": confirmed_balance,
                        "type": addr_type
                    }
                    
                    total_balance += confirmed_balance
                    logging.info(f"Successfully retrieved balance for {addr_type} address {address}")
                except Exception as e:
                    logging.error(f"Error processing address {address}: {str(e)}")
                    balances[address] = {
                        "error": str(e),
                        "type": get_address_type(address)
                    }

            # Restore any frozen UTXOs that weren't found in the scan
            for frozen_utxo in frozen_utxos.values():
                utxo_key = (frozen_utxo.txid, frozen_utxo.vout)
                if utxo_key not in unfrozen_utxos:
                    self.database.store_utxo(frozen_utxo)
                    logging.info(f"Restored frozen UTXO: {frozen_utxo.txid}:{frozen_utxo.vout}")

            # Update wallet balance
            self.database.update_wallet_balance(name, Decimal(str(total_balance)))

            # Only display if not suppressed
            if not suppress_output:
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
                "addresses": balances
            }

        except Exception as e:
            logging.error(f"Error getting balance: {str(e)}")
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
            address_type = wallet_data.get("address_type", "legacy")
            logging.info(f"Network: {network}, Address Type: {address_type}")
            
            # Get RPC configuration
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))
            logging.info(f"RPC connection details - Host: {rpc_host}, Port: {rpc_port}")

            # Create RPC connection and test it first
            try:
                rpc_connection = AuthServiceProxy(
                    f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
                )
                # Test connection with a simple call
                rpc_connection.getblockcount()
            except Exception as e:
                if "Connection refused" in str(e):
                    raise ValueError(
                        "Bitcoin Core is not running or RPC is not properly configured.\n"
                        "Please ensure:\n"
                        "1. Bitcoin Core is running\n"
                        "2. RPC is enabled in bitcoin.conf:\n"
                        "   server=1\n"
                        "   rpcuser=your_rpc_user\n"
                        "   rpcpassword=your_rpc_password\n"
                        "   rpcallowip=127.0.0.1\n"
                        "3. Environment variables are set:\n"
                        "   BITCOIN_RPC_USER\n"
                        "   BITCOIN_RPC_PASSWORD\n"
                        "   BITCOIN_RPC_HOST\n"
                        "   BITCOIN_RPC_PORT"
                    )
                raise

            logging.info("RPC connection established")

            # Get all UTXOs first
            all_utxos = self.get_utxos(name, include_frozen=True)
            if not all_utxos:
                raise ValueError("No UTXOs available")
            
            # Filter out frozen UTXOs
            utxos = [utxo for utxo in all_utxos if not utxo.frozen]
            frozen_count = len(all_utxos) - len(utxos)
            if frozen_count > 0:
                logging.info(f"Skipping {frozen_count} frozen UTXOs")
            
            if not utxos:
                raise ValueError("No unfrozen UTXOs available for spending")

            total_available = sum(utxo.amount for utxo in utxos)
            if total_available < amount:
                raise ValueError(f"Insufficient unfrozen funds. Available: {total_available}, Required: {amount}")
            logging.info(f"Total available from unfrozen UTXOs: {total_available}, Amount to send: {amount}")

            # Generate a change address
            change_address = self.generate_address(name, quiet=True)
            logging.info(f"Generated change address: {change_address}")

            # Create raw inputs
            inputs = []
            input_amount = Decimal('0')
            input_addresses = []
            selected_utxos = []

            # Add inputs until we have enough funds
            for utxo in utxos:
                if utxo.frozen:
                    logging.info(f"Skipping frozen UTXO: {utxo.txid}:{utxo.vout}")
                    continue
                
                inputs.append({
                    "txid": utxo.txid,
                    "vout": utxo.vout
                })
                input_amount += utxo.amount
                input_addresses.append(utxo.address)
                selected_utxos.append(utxo)
                logging.info(f"Added input - TXID: {utxo.txid}, Vout: {utxo.vout}, Amount: {utxo.amount}, Address: {utxo.address}")
                
                # Break if we have enough funds (considering potential fee)
                if input_amount >= amount + Decimal('0.001'):  # Add buffer for fee
                    break

            if not inputs:
                raise ValueError("No suitable UTXOs found for creating the transaction")

            # Create outputs
            outputs = {}
            
            # Payment output - convert Decimal to float with 8 decimal places
            outputs[to_address] = float(amount)

            try:
                # Create raw transaction
                raw_tx = rpc_connection.createrawtransaction(inputs, outputs)
                
                # Get private keys for signing
                private_keys = []
                address_map = {}  # Map addresses to their indices
                for i, addr in enumerate(wallet_data["addresses"]):
                    address_map[addr] = i

                # Decrypt mnemonic once
                mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
                hd_wallet = HDWallet(symbol=BTC)
                hd_wallet.from_mnemonic(mnemonic=mnemonic)

                for addr in input_addresses:
                    if addr not in address_map:
                        raise ValueError(f"Address {addr} not found in wallet")
                    
                    # Get the correct index for this address
                    addr_index = address_map[addr]
                    path = self._get_derivation_path(network, address_type, addr_index)
                    logging.info(f"Using path {path} for address {addr}")

                    # Generate private key
                    hd_wallet.clean_derivation()
                    hd_wallet.from_path(path)
                    private_key_hex = hd_wallet.private_key()
                    private_key = PrivateKey(secret_exponent=int(private_key_hex, 16))
                    wif = private_key.to_wif()
                    private_keys.append(wif)
                    logging.info(f"Generated private key for address {addr} (path: {path})")

                if not private_keys:
                    raise ValueError("No private keys found for the input addresses")

                logging.info(f"Generated {len(private_keys)} private keys for {len(input_addresses)} input addresses")

                # Sign the transaction
                signed_tx = rpc_connection.signrawtransactionwithkey(raw_tx, private_keys)
                if not signed_tx["complete"]:
                    logging.error(f"Failed to sign transaction. Inputs: {json.dumps(inputs, indent=2)}")
                    logging.error(f"Private keys count: {len(private_keys)}")
                    logging.error(f"Input addresses: {input_addresses}")
                    logging.error(f"Wallet addresses: {wallet_data['addresses']}")
                    raise ValueError(
                        "Failed to sign transaction. This could be due to:\n"
                        "1. Incorrect private keys\n"
                        "2. Missing private keys\n"
                        "3. Incompatible address types\n"
                        "Please check the wallet configuration and try again."
                    )

                # Get the size of the signed transaction
                tx_size = len(signed_tx["hex"]) // 2  # Convert from hex to bytes
                
                # Calculate minimum fee based on size and fee rate
                fee_rate = fee_rate if fee_rate is not None else 5.0  # Default to 5 sat/vB
                min_fee_sats = int(tx_size * fee_rate)
                min_fee_btc = Decimal(str(min_fee_sats)) / Decimal('100000000')
                
                # Calculate change amount
                change_amount = input_amount - amount - min_fee_btc
                
                # If we have change worth sending (more than dust), add it to outputs
                if change_amount > Decimal('0.00000546'):  # 546 sats dust limit
                    outputs[change_address] = float(change_amount)
                else:
                    # If change is dust, add it to the fee
                    min_fee_btc += change_amount
                
                # Recreate transaction with proper fee
                raw_tx = rpc_connection.createrawtransaction(inputs, outputs)
                signed_tx = rpc_connection.signrawtransactionwithkey(raw_tx, private_keys)
                if not signed_tx["complete"]:
                    raise ValueError("Failed to sign final transaction")

                # Send the transaction
                txid = rpc_connection.sendrawtransaction(signed_tx["hex"])
                logging.info(f"Transaction sent successfully: {txid}")

                # Store transaction record
                tx_obj = Transaction(
                    txid=txid,
                    timestamp=int(time.time()),
                    amount=amount,
                    fee=min_fee_btc,
                    memo=memo,
                    from_addresses=input_addresses,
                    to_addresses=[to_address],
                    wallet_name=name,
                    change_address=change_address if change_amount > Decimal('0.00000546') else None,
                    status="pending"
                )
                self.database.store_transaction(tx_obj)

                # Update UTXO tracking - only remove the UTXOs we actually used
                for utxo in selected_utxos:
                    self.database.remove_utxo(utxo.txid, utxo.vout)
                    logging.info(f"Removed spent UTXO: {utxo.txid}:{utxo.vout}")

                console.print(f"\n[green]Transaction sent successfully![/green]")
                console.print(f"[yellow]TXID:[/yellow] {txid}")
                console.print(f"[yellow]Amount:[/yellow] {amount} BTC")
                console.print(f"[yellow]Fee:[/yellow] {min_fee_btc} BTC ({min_fee_sats} sats, {fee_rate} sat/vB)")
                if memo:
                    console.print(f"[yellow]Memo:[/yellow] {memo}")

                return txid

            except Exception as e:
                if "Connection refused" in str(e):
                    raise ValueError("Lost connection to Bitcoin Core. Please ensure Bitcoin Core is running and RPC is properly configured.")
                raise

        except Exception as e:
            logging.error(f"Error sending bitcoin: {str(e)}")
            raise

    def create_and_freeze_utxo(self, name: str, amount: Decimal, memo: Optional[str] = None, fee_rate: float = 1.0) -> str:
        """Create a UTXO with specific value and freeze it"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")

            # Check RPC connection first
            network = wallet_data.get("network", "mainnet")
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            try:
                rpc_connection = AuthServiceProxy(
                    f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
                )
                # Test connection with a simple call
                block_count = rpc_connection.getblockcount()
                logging.info(f"Connected to Bitcoin Core (block height: {block_count})")
            except Exception as e:
                if "Connection refused" in str(e):
                    raise ValueError(
                        "Bitcoin Core is not running or RPC is not properly configured.\n"
                        "Please ensure:\n"
                        "1. Bitcoin Core is running (bitcoind -regtest)\n"
                        "2. RPC is enabled in bitcoin.conf:\n"
                        "   server=1\n"
                        "   regtest=1\n"
                        "   rpcuser=your_rpc_user\n"
                        "   rpcpassword=your_rpc_password\n"
                        "   rpcallowip=127.0.0.1\n"
                        "3. Environment variables are set:\n"
                        "   BITCOIN_RPC_USER=your_rpc_user\n"
                        "   BITCOIN_RPC_PASSWORD=your_rpc_password\n"
                        "   BITCOIN_RPC_HOST=127.0.0.1\n"
                        "   BITCOIN_RPC_PORT=18443"
                    )
                raise

            # Get all available UTXOs
            all_utxos = self.get_utxos(name, include_frozen=True)
            if not all_utxos:
                raise ValueError("No UTXOs available")

            # Filter out frozen and immature UTXOs
            available_utxos = []
            for utxo in all_utxos:
                if utxo.frozen:
                    logging.info(f"Skipping frozen UTXO: {utxo.txid}:{utxo.vout}")
                    continue
                if utxo.is_coinbase and (utxo.confirmations or 0) < 100:
                    logging.info(f"Skipping immature coinbase UTXO: {utxo.txid}:{utxo.vout}")
                    continue
                available_utxos.append(utxo)

            if not available_utxos:
                raise ValueError("No spendable UTXOs available")

            # Sort UTXOs by amount in descending order
            available_utxos.sort(key=lambda x: x.amount, reverse=True)

            # Calculate minimum required amount (including estimated fee)
            estimated_size = 180 + 34 + 10  # One input + one output + overhead
            min_fee = Decimal(str(estimated_size * fee_rate)) / Decimal('100000000')
            required_amount = amount + min_fee

            # Select UTXOs (try to minimize the number of inputs)
            selected_utxos = []
            total_input = Decimal('0')

            # First try to find a single UTXO that's close to our target
            for utxo in available_utxos:
                if utxo.amount >= required_amount and utxo.amount <= required_amount * Decimal('1.5'):
                    selected_utxos = [utxo]
                    total_input = utxo.amount
                    break

            # If no suitable single UTXO found, use multiple UTXOs
            if not selected_utxos:
                for utxo in available_utxos:
                    selected_utxos.append(utxo)
                    total_input += utxo.amount
                    estimated_size = (len(selected_utxos) * 180) + 34 + 10
                    min_fee = Decimal(str(estimated_size * fee_rate)) / Decimal('100000000')
                    if total_input >= amount + min_fee:
                        break

            if not selected_utxos:
                raise ValueError("Insufficient funds to create UTXO")

            # Generate a new address for the UTXO
            freeze_address = self.generate_address(name, quiet=True)
            logging.info(f"Generated freeze address: {freeze_address}")

            # Create inputs
            inputs = []
            input_addresses = []
            for utxo in selected_utxos:
                inputs.append({
                    "txid": utxo.txid,
                    "vout": utxo.vout
                })
                input_addresses.append(utxo.address)
                logging.info(f"Using input UTXO: {utxo.txid}:{utxo.vout} ({utxo.amount} BTC) from {utxo.address}")

            # Calculate actual fee based on final transaction size
            tx_size = (len(inputs) * 180) + 34 + 10
            fee = Decimal(str(tx_size * fee_rate)) / Decimal('100000000')
            logging.info(f"Calculated fee: {fee} BTC for {tx_size} bytes at {fee_rate} sat/vB")

            # Create outputs
            outputs = {
                freeze_address: float(amount)
            }

            # Add change output if needed
            change_amount = total_input - amount - fee
            if change_amount > Decimal('0.00000546'):  # More than dust
                change_address = self.generate_address(name, quiet=True)
                outputs[change_address] = float(change_amount)
                logging.info(f"Adding change output: {change_amount} BTC to {change_address}")

            # Create and sign transaction
            try:
                raw_tx = rpc_connection.createrawtransaction(inputs, outputs)
                logging.info("Created raw transaction")

                # Get private keys for signing
                private_keys = []
                address_indices = {}  # Map addresses to all their indices
                
                # Build a map of all addresses and their indices
                for i, addr in enumerate(wallet_data["addresses"]):
                    if addr not in address_indices:
                        address_indices[addr] = []
                    address_indices[addr].append(i)

                # Decrypt mnemonic once
                mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
                hd_wallet = HDWallet(symbol=BTC)
                hd_wallet.from_mnemonic(mnemonic=mnemonic)

                # Try all possible derivation paths for each input address
                for addr in input_addresses:
                    if addr not in address_indices:
                        raise ValueError(f"Address {addr} not found in wallet")
                    
                    # Get all indices for this address
                    indices = address_indices[addr]
                    logging.info(f"Found {len(indices)} possible indices for address {addr}")
                    
                    key_found = False
                    # Try each possible derivation path
                    for idx in indices:
                        path = self._get_derivation_path(network, wallet_data.get("address_type", "legacy"), idx)
                        logging.info(f"Trying path {path} for address {addr}")

                        # Generate private key
                        hd_wallet.clean_derivation()
                        hd_wallet.from_path(path)
                        private_key_hex = hd_wallet.private_key()
                        private_key = PrivateKey(secret_exponent=int(private_key_hex, 16))
                        
                        # Verify this private key corresponds to the address
                        pubkey = private_key.get_public_key()
                        derived_addr = pubkey.get_address().to_string()
                        
                        if derived_addr == addr:
                            wif = private_key.to_wif()
                            private_keys.append(wif)
                            logging.info(f"Found matching private key for address {addr} at path {path}")
                            key_found = True
                            break
                    
                    if not key_found:
                        raise ValueError(f"Could not find private key for address {addr}")

                if len(private_keys) != len(input_addresses):
                    raise ValueError(f"Could not find all private keys. Found {len(private_keys)} of {len(input_addresses)} required keys")

                # Sign transaction
                signed_tx = rpc_connection.signrawtransactionwithkey(raw_tx, private_keys)
                if not signed_tx["complete"]:
                    logging.error(f"Failed to sign transaction. Inputs: {json.dumps(inputs, indent=2)}")
                    logging.error(f"Private keys count: {len(private_keys)}")
                    logging.error(f"Input addresses: {input_addresses}")
                    logging.error(f"Wallet addresses: {wallet_data['addresses']}")
                    
                    if "errors" in signed_tx:
                        for error in signed_tx["errors"]:
                            logging.error(f"Signing error: {json.dumps(error, indent=2)}")
                    
                    raise ValueError("Failed to sign transaction")

                # Send transaction
                txid = rpc_connection.sendrawtransaction(signed_tx["hex"])
                logging.info(f"Transaction sent: {txid}")

                # Create and store the frozen UTXO
                frozen_utxo = UTXO(
                    txid=txid,
                    vout=0,  # The frozen output is always first
                    amount=amount,
                    address=freeze_address,
                    frozen=True,
                    memo=memo,
                    wallet_name=name
                )
                self.database.store_utxo(frozen_utxo)
                logging.info(f"Stored frozen UTXO: {txid}:0")

                # Remove spent UTXOs
                for utxo in selected_utxos:
                    self.database.remove_utxo(utxo.txid, utxo.vout)
                    logging.info(f"Removed spent UTXO: {utxo.txid}:{utxo.vout}")

                # Store transaction record
                tx_obj = Transaction(
                    txid=txid,
                    timestamp=int(time.time()),
                    amount=amount,
                    fee=fee,
                    memo=f"Created frozen UTXO: {memo}" if memo else "Created frozen UTXO",
                    from_addresses=input_addresses,
                    to_addresses=[freeze_address],
                    wallet_name=name,
                    change_address=change_address if change_amount > Decimal('0.00000546') else None,
                    status="pending"
                )
                self.database.store_transaction(tx_obj)

                console.print(f"\n[green]Created and froze UTXO successfully![/green]")
                console.print(f"[yellow]TXID:[/yellow] {txid}")
                console.print(f"[yellow]Amount:[/yellow] {amount} BTC")
                console.print(f"[yellow]Fee:[/yellow] {fee} BTC")
                console.print(f"[yellow]Address:[/yellow] {freeze_address}")
                if memo:
                    console.print(f"[yellow]Memo:[/yellow] {memo}")

                return txid

            except Exception as e:
                if "Connection refused" in str(e):
                    raise ValueError("Lost connection to Bitcoin Core. Please ensure Bitcoin Core is running and RPC is properly configured.")
                raise

        except Exception as e:
            logging.error(f"Error creating frozen UTXO: {str(e)}")
            raise

    def _wait_for_confirmation(self, txid: str, confirmations: int = 1, timeout: int = 60):
        """Wait for a transaction to get the required number of confirmations with timeout"""
        try:
            network = self.network
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )

            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    tx = rpc_connection.getrawtransaction(txid, True)
                    if "confirmations" in tx and tx["confirmations"] >= confirmations:
                        return True
                except Exception as e:
                    if "No such mempool or blockchain transaction" in str(e):
                        # Transaction not found yet, continue waiting
                        pass
                    else:
                        logging.error(f"Error checking transaction: {str(e)}")
                        raise
                
                # If in regtest mode, warn about mining blocks
                if network == "regtest" and time.time() - start_time > 5:
                    console.print("[yellow]Waiting for confirmation. In regtest mode, you need to mine blocks manually.[/yellow]")
                    console.print("[yellow]Use bitcoin-cli generatetoaddress 1 <address> to mine a block.[/yellow]")
                    return False
                
                time.sleep(1)  # Wait for 1 second before checking again
            
            # If we reach here, we timed out
            logging.warning(f"Timeout waiting for confirmation of transaction {txid}")
            return False

        except Exception as e:
            logging.error(f"Error waiting for confirmation: {str(e)}")
            raise

    def get_utxos(self, wallet_name: str, include_frozen: bool = False) -> List[UTXO]:
        """Get all UTXOs for a wallet"""
        try:
            network = self.network
            utxos = self.database.get_utxos(wallet_name, include_frozen=include_frozen)
            
            # Try to establish RPC connection first
            try:
                rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
                rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
                rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
                rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

                rpc_connection = AuthServiceProxy(
                    f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
                )
                
                # Test connection with a simple call
                rpc_connection.getblockcount()
                
                # If we get here, RPC is working
                required_depth = 100  # Both regtest and mainnet require 100 blocks
                mature_utxos = []
                
                for utxo in utxos:
                    try:
                        # Get transaction details
                        tx = rpc_connection.getrawtransaction(utxo.txid, True)
                        
                        # Check if it's a coinbase transaction
                        is_coinbase = any(vin.get("coinbase") for vin in tx.get("vin", []))
                        confirmations = tx.get("confirmations", 0)
                        
                        # Update UTXO with confirmation info
                        utxo.is_coinbase = is_coinbase
                        utxo.confirmations = confirmations
                        
                        # If it's coinbase, check maturity
                        if is_coinbase and confirmations < required_depth:
                            logging.info(f"Skipping immature coinbase UTXO {utxo.txid}:{utxo.vout} (depth: {confirmations})")
                            continue
                        
                        mature_utxos.append(utxo)
                    except Exception as e:
                        if "No such mempool or blockchain transaction" in str(e):
                            logging.info(f"UTXO {utxo.txid} not found in blockchain or mempool, skipping")
                            continue
                        else:
                            logging.error(f"Error checking UTXO {utxo.txid}: {str(e)}")
                            # Still include the UTXO but without confirmation info
                            mature_utxos.append(utxo)
                
                return mature_utxos
                
            except Exception as e:
                # If RPC connection fails, return UTXOs without confirmation info
                logging.warning(f"RPC connection failed: {str(e)}")
                return utxos

        except Exception as e:
            logging.error(f"Error getting UTXOs: {str(e)}")
            return []

    def consolidate_utxos(self, name: str, fee_rate: float = 5.0, batch_size: int = 50) -> Optional[str]:
        """Consolidate unfrozen UTXOs into a single UTXO, processing in batches if needed"""
        try:
            name = self._validate_wallet_name(name)
            wallet_data = self._load_wallet(name)
            if not wallet_data:
                raise ValueError(f"Wallet '{name}' not found")

            # Get all unfrozen UTXOs
            all_utxos = self.get_utxos(name, include_frozen=True)
            if not all_utxos:
                raise ValueError("No UTXOs available")

            # Filter out frozen UTXOs
            utxos = [utxo for utxo in all_utxos if not utxo.frozen]
            frozen_count = len(all_utxos) - len(utxos)
            
            if frozen_count > 0:
                logging.info(f"Skipping {frozen_count} frozen UTXOs")
            
            if not utxos:
                raise ValueError("No unfrozen UTXOs available for consolidation")
            
            if len(utxos) < 2:
                raise ValueError("Need at least 2 unfrozen UTXOs to consolidate")

            # Sort UTXOs by amount in descending order
            utxos.sort(key=lambda x: x.amount, reverse=True)
            
            # Take only batch_size UTXOs
            utxos = utxos[:batch_size]
            logging.info(f"Processing batch of {len(utxos)} UTXOs")

            network = wallet_data.get("network", "mainnet")
            address_type = wallet_data.get("address_type", "legacy")
            logging.info(f"Network: {network}, Address Type: {address_type}")
            
            # Get RPC configuration
            rpc_user = os.getenv("BITCOIN_RPC_USER", "user")
            rpc_password = os.getenv("BITCOIN_RPC_PASSWORD", "pass")
            rpc_host = os.getenv("BITCOIN_RPC_HOST", "127.0.0.1")
            rpc_port = int(os.getenv("BITCOIN_RPC_PORT", self.default_ports[network]))

            # Create RPC connection
            rpc_connection = AuthServiceProxy(
                f"http://{rpc_user}:{rpc_password}@{rpc_host}:{rpc_port}"
            )

            # Calculate total amount
            total_amount = sum(utxo.amount for utxo in utxos)
            logging.info(f"Total amount to consolidate: {total_amount} BTC")
            
            # Generate a new address for the consolidated UTXO
            consolidated_address = self.generate_address(name, quiet=True)
            logging.info(f"Generated consolidated address: {consolidated_address}")

            # Create inputs from unfrozen UTXOs
            inputs = []
            input_addresses = []
            for utxo in utxos:
                inputs.append({
                    "txid": utxo.txid,
                    "vout": utxo.vout
                })
                input_addresses.append(utxo.address)

            # Estimate transaction size and fee
            estimated_size = (len(inputs) * 180) + 34 + 10  # inputs + 1 output + overhead
            fee = Decimal(str(estimated_size * fee_rate)) / Decimal('100000000')
            logging.info(f"Estimated fee: {fee} BTC (size: {estimated_size} bytes, rate: {fee_rate} sat/vB)")
            
            # Create output (total amount minus fee)
            consolidated_amount = total_amount - fee
            if consolidated_amount <= 0:
                raise ValueError(f"Fee would exceed total amount. Try a lower fee rate or consolidate larger UTXOs")

            outputs = {
                consolidated_address: float(consolidated_amount)
            }

            # Create raw transaction
            raw_tx = rpc_connection.createrawtransaction(inputs, outputs)
            
            # Get private keys for signing
            private_keys = []
            address_indices = {}  # Map addresses to all their indices
            
            # Build a map of all addresses and their indices
            for i, addr in enumerate(wallet_data["addresses"]):
                if addr not in address_indices:
                    address_indices[addr] = []
                address_indices[addr].append(i)

            # Decrypt mnemonic once
            mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
            hd_wallet = HDWallet(symbol=BTC)
            hd_wallet.from_mnemonic(mnemonic=mnemonic)

            # Try all possible derivation paths for each input address
            for addr in input_addresses:
                if addr not in address_indices:
                    raise ValueError(f"Address {addr} not found in wallet")
                
                # Get all indices for this address
                indices = address_indices[addr]
                logging.info(f"Found {len(indices)} possible indices for address {addr}")
                
                key_found = False
                # Try each possible derivation path
                for idx in indices:
                    path = self._get_derivation_path(network, address_type, idx)
                    logging.info(f"Trying path {path} for address {addr}")

                    # Generate private key
                    hd_wallet.clean_derivation()
                    hd_wallet.from_path(path)
                    private_key_hex = hd_wallet.private_key()
                    private_key = PrivateKey(secret_exponent=int(private_key_hex, 16))
                    
                    # Verify this private key corresponds to the address
                    pubkey = private_key.get_public_key()
                    derived_addr = pubkey.get_address().to_string()
                    
                    if derived_addr == addr:
                        wif = private_key.to_wif()
                        private_keys.append(wif)
                        logging.info(f"Found matching private key for address {addr} at path {path}")
                        key_found = True
                        break
                
                if not key_found:
                    raise ValueError(f"Could not find private key for address {addr}")

            if len(private_keys) != len(input_addresses):
                raise ValueError(f"Could not find all private keys. Found {len(private_keys)} of {len(input_addresses)} required keys")

            # Sign transaction
            signed_tx = rpc_connection.signrawtransactionwithkey(raw_tx, private_keys)
            if not signed_tx["complete"]:
                logging.error(f"Failed to sign consolidation transaction. Inputs: {json.dumps(inputs, indent=2)}")
                logging.error(f"Private keys count: {len(private_keys)}")
                logging.error(f"Input addresses: {input_addresses}")
                logging.error(f"Wallet addresses: {wallet_data['addresses']}")
                
                if "errors" in signed_tx:
                    for error in signed_tx["errors"]:
                        logging.error(f"Signing error: {json.dumps(error, indent=2)}")
                
                raise ValueError("Failed to sign consolidation transaction")

            # Send transaction
            txid = rpc_connection.sendrawtransaction(signed_tx["hex"])
            logging.info(f"Consolidation transaction sent: {txid}")

            # Update UTXO tracking - remove the UTXOs that were consolidated
            for utxo in utxos:
                self.database.remove_utxo(utxo.txid, utxo.vout)
                logging.info(f"Removed spent UTXO from database: {utxo.txid}:{utxo.vout}")

            # Store the new consolidated UTXO
            consolidated_utxo = UTXO(
                txid=txid,
                vout=0,  # First and only output
                amount=consolidated_amount,
                address=consolidated_address,
                frozen=False,
                wallet_name=name
            )
            self.database.store_utxo(consolidated_utxo)
            logging.info(f"Stored new consolidated UTXO: {txid}:0 ({consolidated_amount} BTC)")

            # Store transaction record
            tx_obj = Transaction(
                txid=txid,
                timestamp=int(time.time()),
                amount=consolidated_amount,
                fee=fee,
                memo="UTXO Consolidation",
                from_addresses=input_addresses,
                to_addresses=[consolidated_address],
                wallet_name=name,
                change_address=None,
                status="pending"
            )
            self.database.store_transaction(tx_obj)

            return txid

        except Exception as e:
            logging.error(f"Error consolidating UTXOs: {str(e)}")
            raise ValueError(f"Failed to consolidate UTXOs: {str(e)}")

    def delete_wallet(self, name: str) -> bool:
        """Delete a wallet and all its associated data"""
        try:
            name = self._validate_wallet_name(name)
            wallet_file = self.wallets_dir / f"{name}.json"
            
            if not wallet_file.exists():
                raise ValueError(f"Wallet '{name}' not found")
            
            # Delete the wallet file
            wallet_file.unlink()
            
            # Delete any associated UTXOs and transactions from database
            self.database.delete_wallet_data(name)
            
            return True
            
        except Exception as e:
            logging.error(f"Error deleting wallet '{name}': {str(e)}")
            raise

    def get_frozen_utxos(self, wallet_name: str) -> List[UTXO]:
        """Get all frozen UTXOs for a wallet"""
        try:
            # Get UTXOs from database that are marked as frozen
            frozen_utxos = self.database.get_utxos(wallet_name, include_frozen=True)
            return [utxo for utxo in frozen_utxos if utxo.frozen]
        except Exception as e:
            logging.error(f"Error getting frozen UTXOs for wallet {wallet_name}: {str(e)}")
            return []

    def get_addresses(self, wallet_name: str) -> List[Dict[str, Any]]:
        """Get all addresses for a wallet with their details."""
        try:
            logging.info(f"Getting addresses for wallet: {wallet_name}")
            wallet = self.get_wallet(wallet_name)
            if not wallet:
                raise ValueError(f"Wallet '{wallet_name}' not found")
            
            addresses = []
            network = wallet.get('network', 'mainnet')
            address_type = wallet.get('address_type', 'legacy')
            address_index = wallet.get('address_index', 0)
            
            logging.info(f"Wallet info - Network: {network}, Type: {address_type}, Index: {address_index}")
            
            # Decrypt mnemonic
            mnemonic = self.fernet.decrypt(wallet['encrypted_mnemonic'].encode()).decode()
            hd_wallet = HDWallet(symbol=BTC)
            hd_wallet.from_mnemonic(mnemonic=mnemonic)
            
            # Get addresses from wallet data
            for i in range(address_index + 1):
                logging.info(f"Processing address {i} of {address_index}")
                # Get derivation path
                path = self._get_derivation_path(network, address_type, i)
                logging.info(f"Using derivation path: {path}")
                
                # Generate keys
                hd_wallet.clean_derivation()
                hd_wallet.from_path(path)
                private_key_hex = hd_wallet.private_key()
                private_key = PrivateKey(secret_exponent=int(private_key_hex, 16))
                public_key = private_key.get_public_key()
                
                # Get address based on type
                if address_type == 'taproot':
                    pubkey_hex = public_key.to_hex()
                    address = create_p2tr_address(pubkey_hex, network)
                else:
                    address = _get_address_from_private_key(private_key, network, address_type)
                
                logging.info(f"Generated address: {address}")
                
                addresses.append({
                    'address': address,
                    'derivation_path': path,
                    'public_key': public_key.to_hex(),
                    'private_key': private_key.to_wif()
                })
            
            logging.info(f"Total addresses generated: {len(addresses)}")
            return addresses
            
        except Exception as e:
            logging.error(f"Error getting addresses for wallet {wallet_name}: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to get addresses: {str(e)}")

# Create a global instance
wallet_manager = WalletManager() 