from bitcoinrpc.authproxy import AuthServiceProxy
from typing import List, Dict, Optional
import logging
from .config import get_settings

settings = get_settings()

class BitcoinClient:
    """Bitcoin node client for transaction operations only.
    This client does not handle wallet operations, which are managed by our own wallet implementation."""
    
    def __init__(self):
        self.rpc_connection = self._get_rpc_connection()
    
    def _get_rpc_connection(self):
        """Get RPC connection to Bitcoin node"""
        rpc_url = f"http://{settings.bitcoin_rpc_user}:{settings.bitcoin_rpc_password}@{settings.bitcoin_rpc_host}:{settings.bitcoin_rpc_port}"
        return AuthServiceProxy(rpc_url)
    
    def broadcast_transaction(self, raw_tx: str) -> str:
        """Broadcast a raw transaction to the network"""
        try:
            txid = self.rpc_connection.sendrawtransaction(raw_tx)
            return txid
        except Exception as e:
            logging.error(f"Error broadcasting transaction: {str(e)}")
            raise Exception(f"Failed to broadcast transaction: {str(e)}")
    
    def get_transaction(self, txid: str) -> Dict:
        """Get transaction details"""
        try:
            return self.rpc_connection.getrawtransaction(txid, True)
        except Exception as e:
            logging.error(f"Error getting transaction: {str(e)}")
            raise Exception(f"Failed to get transaction: {str(e)}")
    
    def get_utxo(self, txid: str, vout: int) -> Optional[Dict]:
        """Get UTXO details if it exists and is unspent"""
        try:
            return self.rpc_connection.gettxout(txid, vout)
        except Exception as e:
            logging.error(f"Error getting UTXO: {str(e)}")
            return None
    
    def get_network_info(self) -> Dict:
        """Get current network information"""
        try:
            return self.rpc_connection.getnetworkinfo()
        except Exception as e:
            logging.error(f"Error getting network info: {str(e)}")
            raise Exception(f"Failed to get network info: {str(e)}")
    
    def get_block_height(self) -> int:
        """Get current block height"""
        try:
            return self.rpc_connection.getblockcount()
        except Exception as e:
            logging.error(f"Error getting block height: {str(e)}")
            raise Exception(f"Failed to get block height: {str(e)}")

# Create a global instance
bitcoin_client = BitcoinClient() 