from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from .database import Database
from .utxo_manager import UTXOManager
from .schemas import (
    validate_token_schema,
    validate_transfer_schema,
    validate_burn_schema,
    TokenSchemaVersion
)
from .logging_config import logger

class TokenOperations:
    def __init__(self, db: Database, utxo_manager: UTXOManager):
        self.db = db
        self.utxo_manager = utxo_manager

    def transfer_token(self, transfer_data: Dict[str, Any]) -> bool:
        """
        Transfer a token from one address to another
        """
        try:
            # Validate transfer data
            validate_transfer_schema(transfer_data)

            # Get token data
            token = self.db.get_token_by_id(transfer_data['token_id'])
            if not token:
                raise ValueError("Token not found")

            # Verify UTXO ownership
            if not self.utxo_manager.verify_ownership(
                transfer_data['utxo']['txid'],
                transfer_data['utxo']['vout'],
                transfer_data['from_address'],
                transfer_data['signature']
            ):
                raise ValueError("Invalid UTXO ownership")

            # Lock new UTXO
            if not self.utxo_manager.lock_utxo(
                transfer_data['utxo']['txid'],
                transfer_data['utxo']['vout'],
                transfer_data['to_address'],
                transfer_data['token_id']
            ):
                raise ValueError("Failed to lock UTXO")

            # Update token ownership
            token['owner_address'] = transfer_data['to_address']
            token['utxo'] = transfer_data['utxo']
            token['updated_at'] = datetime.utcnow().isoformat()

            # Store updated token
            self.db.update_token(token)

            # Record transfer in history
            self._record_token_history(
                token['token_id'],
                "transfer",
                transfer_data['from_address'],
                transfer_data['to_address'],
                transfer_data
            )

            return True
        except Exception as e:
            logger.error(f"Error transferring token: {str(e)}")
            return False

    def burn_token(self, burn_data: Dict[str, Any]) -> bool:
        """
        Burn a token (destroy it permanently)
        """
        try:
            # Validate burn data
            validate_burn_schema(burn_data)

            # Get token data
            token = self.db.get_token_by_id(burn_data['token_id'])
            if not token:
                raise ValueError("Token not found")

            # Verify token ownership
            if token['owner_address'] != burn_data['owner_address']:
                raise ValueError("Not token owner")

            # Verify UTXO ownership
            if not self.utxo_manager.verify_ownership(
                burn_data['utxo']['txid'],
                burn_data['utxo']['vout'],
                burn_data['owner_address'],
                burn_data['signature']
            ):
                raise ValueError("Invalid UTXO ownership")

            # Mark token as burned
            token['burned'] = True
            token['burned_at'] = datetime.utcnow().isoformat()
            token['updated_at'] = datetime.utcnow().isoformat()

            # Store updated token
            self.db.update_token(token)

            # Record burn in history
            self._record_token_history(
                token['token_id'],
                "burn",
                burn_data['owner_address'],
                None,
                burn_data
            )

            return True
        except Exception as e:
            logger.error(f"Error burning token: {str(e)}")
            return False

    def update_token_metadata(
        self,
        token_id: str,
        metadata: Dict[str, Any],
        owner_address: str,
        signature: str
    ) -> bool:
        """
        Update token metadata
        """
        try:
            # Get token data
            token = self.db.get_token_by_id(token_id)
            if not token:
                raise ValueError("Token not found")

            # Verify token ownership
            if token['owner_address'] != owner_address:
                raise ValueError("Not token owner")

            # Verify signature
            message = json.dumps(metadata, sort_keys=True)
            if not self.utxo_manager.verify_ownership(
                token['utxo']['txid'],
                token['utxo']['vout'],
                owner_address,
                signature
            ):
                raise ValueError("Invalid signature")

            # Update metadata
            token['metadata'].update(metadata)
            token['updated_at'] = datetime.utcnow().isoformat()

            # Store updated token
            self.db.update_token(token)

            # Record metadata update in history
            self._record_token_history(
                token_id,
                "metadata_update",
                owner_address,
                None,
                metadata
            )

            return True
        except Exception as e:
            logger.error(f"Error updating token metadata: {str(e)}")
            return False

    def get_token_history(self, token_id: str) -> List[Dict[str, Any]]:
        """
        Get the history of a token
        """
        try:
            return self.db.get_token_history(token_id)
        except Exception as e:
            logger.error(f"Error getting token history: {str(e)}")
            return []

    def _record_token_history(
        self,
        token_id: str,
        action: str,
        from_address: str,
        to_address: Optional[str],
        data: Dict[str, Any]
    ) -> bool:
        """
        Record a token action in the history
        """
        try:
            history_entry = {
                'token_id': token_id,
                'action': action,
                'from_address': from_address,
                'to_address': to_address,
                'data': json.dumps(data),
                'timestamp': datetime.utcnow().isoformat()
            }
            return self.db.add_token_history(history_entry)
        except Exception as e:
            logger.error(f"Error recording token history: {str(e)}")
            return False 