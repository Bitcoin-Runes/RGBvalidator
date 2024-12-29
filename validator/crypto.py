from typing import Optional
import hashlib
from bitcoinrpc.authproxy import AuthServiceProxy
from .models import BaseToken
from .config import get_settings

settings = get_settings()

class SignatureValidator:
    def __init__(self):
        self.rpc_connection = self._get_rpc_connection()
    
    def _get_rpc_connection(self) -> AuthServiceProxy:
        """Create a connection to the Bitcoin node"""
        rpc_url = f"http://{settings.BITCOIN_RPC_USER}:{settings.BITCOIN_RPC_PASSWORD}@{settings.BITCOIN_RPC_HOST}:{settings.BITCOIN_RPC_PORT}"
        return AuthServiceProxy(rpc_url)
    
    def create_token_signature(self, token: BaseToken, wallet_name: str) -> str:
        """Create a signature for a token using the wallet's private key"""
        # Create message hash from token data
        token_dict = token.dict()
        token_dict.pop('signature', None)  # Remove existing signature if any
        message = hashlib.sha256(str(token_dict).encode()).hexdigest()
        
        try:
            # Sign message with wallet's private key
            self.rpc_connection.loadwallet(wallet_name)
            signature = self.rpc_connection.signmessage(
                self.rpc_connection.getnewaddress(),
                message
            )
            return signature
        except Exception as e:
            raise Exception(f"Failed to create signature: {str(e)}")
    
    def verify_token_signature(self, token: BaseToken) -> bool:
        """Verify a token's signature"""
        if not token.signature:
            return False
            
        try:
            # Recreate message hash
            token_dict = token.dict()
            token_dict.pop('signature', None)
            message = hashlib.sha256(str(token_dict).encode()).hexdigest()
            
            # Get wallet's address
            self.rpc_connection.loadwallet(token.wallet_name)
            address = self.rpc_connection.getaddressinfo(
                self.rpc_connection.getnewaddress()
            )['address']
            
            # Verify signature
            return self.rpc_connection.verifymessage(
                address,
                token.signature,
                message
            )
        except Exception as e:
            raise Exception(f"Failed to verify signature: {str(e)}")

# Create a global instance
signature_validator = SignatureValidator() 