from bitcoinrpc.authproxy import AuthServiceProxy
from typing import List, Dict, Optional
import logging
from .config import get_settings

settings = get_settings()

class BitcoinClient:
    def __init__(self):
        self.rpc_connection = self._get_rpc_connection()
    
    def _get_rpc_connection(self) -> AuthServiceProxy:
        """Create a connection to the Bitcoin node"""
        rpc_url = f"http://{settings.BITCOIN_RPC_USER}:{settings.BITCOIN_RPC_PASSWORD}@{settings.BITCOIN_RPC_HOST}:{settings.BITCOIN_RPC_PORT}"
        return AuthServiceProxy(rpc_url)
    
    def create_wallet(self, wallet_name: str) -> Dict:
        """Create a new wallet"""
        try:
            result = self.rpc_connection.createwallet(wallet_name)
            if result.get('name') == wallet_name:
                # Load the wallet
                self.rpc_connection.loadwallet(wallet_name)
                # Generate a new address
                address = self.rpc_connection.getnewaddress()
                return {
                    "wallet_name": wallet_name,
                    "address": address,
                    "status": "created"
                }
        except Exception as e:
            logging.error(f"Error creating wallet: {str(e)}")
            raise Exception(f"Failed to create wallet: {str(e)}")
    
    def get_wallet_balance(self, wallet_name: str) -> float:
        """Get wallet balance"""
        try:
            self.rpc_connection.loadwallet(wallet_name)
            return self.rpc_connection.getbalance()
        except Exception as e:
            logging.error(f"Error getting balance: {str(e)}")
            raise Exception(f"Failed to get wallet balance: {str(e)}")
    
    def get_utxos(self, wallet_name: str) -> List[Dict]:
        """Get list of UTXOs for a wallet"""
        try:
            self.rpc_connection.loadwallet(wallet_name)
            return self.rpc_connection.listunspent()
        except Exception as e:
            logging.error(f"Error getting UTXOs: {str(e)}")
            raise Exception(f"Failed to get UTXOs: {str(e)}")
    
    def verify_utxo(self, txid: str, vout: int) -> bool:
        """Verify if a UTXO exists and is unspent"""
        try:
            utxo = self.rpc_connection.gettxout(txid, vout)
            return utxo is not None
        except Exception as e:
            logging.error(f"Error verifying UTXO: {str(e)}")
            return False
    
    def get_wallet_address(self, wallet_name: str) -> str:
        """Get a new address for the wallet"""
        try:
            self.rpc_connection.loadwallet(wallet_name)
            return self.rpc_connection.getnewaddress()
        except Exception as e:
            logging.error(f"Error getting address: {str(e)}")
            raise Exception(f"Failed to get wallet address: {str(e)}")

# Create a global instance
bitcoin_client = BitcoinClient() 