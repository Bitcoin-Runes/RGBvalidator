from typing import Dict, List, Optional, Literal
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
from .config import get_settings

settings = get_settings()

# Define network types
NetworkType = Literal["mainnet", "testnet", "regtest"]

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
    
    def _get_network_path(self, network: NetworkType) -> str:
        """Get BIP44 coin type based on network"""
        # BIP44 coin types:
        # 0 for mainnet
        # 1 for testnet/regtest
        coin_type = "0" if network == "mainnet" else "1"
        return f"m/44'/{coin_type}'/0'/0/0"
    
    def create_wallet(self, name: str, network: Optional[NetworkType] = None) -> Dict:
        """Create a new HD wallet with encrypted storage"""
        if self._wallet_exists(name):
            raise Exception(f"Wallet '{name}' already exists")
        
        network = network or self.network
        
        # Generate mnemonic and create wallet
        mnemonic = generate_mnemonic(strength=256)  # 24 words
        wallet = HDWallet(symbol=BTC)
        wallet.from_mnemonic(mnemonic=mnemonic)
        
        # Generate first address
        wallet.clean_derivation()
        path = self._get_network_path(network)
        wallet.from_path(path)
        
        # Get appropriate address based on network
        if network == "mainnet":
            address = wallet.p2pkh_address()  # mainnet address (starts with 1)
        else:
            address = wallet.p2pkh_address(testnet=True)  # testnet address (starts with m or n)
        
        # Prepare wallet data
        wallet_data = {
            "name": name,
            "network": network,
            "encrypted_mnemonic": self.fernet.encrypt(mnemonic.encode()).decode(),
            "addresses": [address],
            "address_index": 1,
            "created_at": str(datetime.datetime.now())
        }
        
        # Save wallet
        self._save_wallet(name, wallet_data)
        
        return {
            "name": name,
            "network": network,
            "address": address,
            "status": "created"
        }
    
    def get_wallet(self, name: str) -> Optional[Dict]:
        """Get wallet information"""
        try:
            return self._load_wallet(name)
        except Exception as e:
            logging.error(f"Error loading wallet: {str(e)}")
            return None
    
    def list_wallets(self) -> List[Dict]:
        """List all available wallets with their networks"""
        wallets = []
        for wallet_file in self.wallets_dir.glob("*.json"):
            try:
                wallet_data = self._load_wallet(wallet_file.stem)
                wallets.append({
                    "name": wallet_data["name"],
                    "network": wallet_data.get("network", "mainnet"),
                    "addresses": wallet_data["addresses"]
                })
            except Exception as e:
                logging.error(f"Error loading wallet {wallet_file.stem}: {str(e)}")
        return wallets
    
    def generate_address(self, name: str) -> str:
        """Generate a new address for the wallet"""
        wallet_data = self._load_wallet(name)
        if not wallet_data:
            raise Exception(f"Wallet '{name}' not found")
        
        network = wallet_data.get("network", "mainnet")
        
        # Decrypt mnemonic and recreate wallet
        mnemonic = self.fernet.decrypt(wallet_data["encrypted_mnemonic"].encode()).decode()
        wallet = HDWallet(symbol=BTC)
        wallet.from_mnemonic(mnemonic=mnemonic)
        
        # Generate new address
        wallet.clean_derivation()
        coin_type = "0" if network == "mainnet" else "1"
        path = f"m/44'/{coin_type}'/0'/0/{wallet_data['address_index']}"
        wallet.from_path(path)
        
        # Get appropriate address based on network
        if network == "mainnet":
            address = wallet.p2pkh_address()
        else:
            address = wallet.p2pkh_address(testnet=True)
        
        # Update wallet data
        wallet_data["addresses"].append(address)
        wallet_data["address_index"] += 1
        self._save_wallet(name, wallet_data)
        
        return address
    
    def _wallet_exists(self, name: str) -> bool:
        """Check if wallet exists"""
        return (self.wallets_dir / f"{name}.json").exists()
    
    def _save_wallet(self, name: str, data: Dict):
        """Save wallet data to file"""
        wallet_file = self.wallets_dir / f"{name}.json"
        with open(wallet_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_wallet(self, name: str) -> Dict:
        """Load wallet data from file"""
        wallet_file = self.wallets_dir / f"{name}.json"
        if not wallet_file.exists():
            raise Exception(f"Wallet '{name}' not found")
        with open(wallet_file, 'r') as f:
            return json.load(f)

# Create a global instance
wallet_manager = WalletManager() 