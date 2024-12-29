from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
from .exceptions import (
    MultiSigError, TimelockError, ReplayProtectionError, 
    DoubleSpendingError, SecurityError
)
from .crypto import SignatureValidator
from .database import Database
from .logging_config import logger

class SecurityManager:
    def __init__(self, db: Database):
        self.db = db
        self.signature_validator = SignatureValidator()

    def verify_multisig(
        self,
        message: str,
        signatures: List[str],
        public_keys: List[str],
        required_signatures: int
    ) -> bool:
        """
        Verify multi-signature requirement
        """
        try:
            if len(signatures) < required_signatures:
                raise MultiSigError(
                    f"Not enough signatures. Required: {required_signatures}, Got: {len(signatures)}"
                )

            valid_signatures = 0
            for sig in signatures:
                for pk in public_keys:
                    if self.signature_validator.verify_signature(message, sig, pk):
                        valid_signatures += 1
                        break

            if valid_signatures < required_signatures:
                raise MultiSigError(
                    f"Invalid signatures. Required: {required_signatures}, Valid: {valid_signatures}"
                )

            return True
        except Exception as e:
            logger.error(f"Multi-signature verification failed: {str(e)}")
            raise MultiSigError("Multi-signature verification failed", {"error": str(e)})

    def verify_timelock(
        self,
        timelock_data: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Verify timelock conditions
        """
        try:
            current_time = current_time or datetime.utcnow()
            
            if 'start_time' in timelock_data:
                start_time = datetime.fromisoformat(timelock_data['start_time'])
                if current_time < start_time:
                    raise TimelockError("Transaction not yet valid", {
                        "current_time": current_time.isoformat(),
                        "start_time": start_time.isoformat()
                    })

            if 'end_time' in timelock_data:
                end_time = datetime.fromisoformat(timelock_data['end_time'])
                if current_time > end_time:
                    raise TimelockError("Transaction expired", {
                        "current_time": current_time.isoformat(),
                        "end_time": end_time.isoformat()
                    })

            return True
        except TimelockError:
            raise
        except Exception as e:
            logger.error(f"Timelock verification failed: {str(e)}")
            raise TimelockError("Timelock verification failed", {"error": str(e)})

    def prevent_replay(self, transaction_data: Dict[str, Any]) -> bool:
        """
        Prevent transaction replay attacks
        """
        try:
            # Create unique transaction hash
            tx_hash = hashlib.sha256(
                str(sorted(transaction_data.items())).encode()
            ).hexdigest()

            # Check if transaction has been processed before
            if self.db.transaction_exists(tx_hash):
                raise ReplayProtectionError(
                    "Transaction already processed",
                    {"transaction_hash": tx_hash}
                )

            # Record transaction
            self.db.record_transaction(tx_hash, transaction_data)
            return True
        except Exception as e:
            logger.error(f"Replay protection failed: {str(e)}")
            raise ReplayProtectionError("Replay protection failed", {"error": str(e)})

    def prevent_double_spending(
        self,
        utxo_data: Dict[str, Any],
        token_id: str
    ) -> bool:
        """
        Prevent double spending of UTXOs
        """
        try:
            txid = utxo_data['txid']
            vout = utxo_data['vout']

            # Check if UTXO is already spent
            if self.db.is_utxo_spent(txid, vout):
                raise DoubleSpendingError(
                    "UTXO already spent",
                    {"txid": txid, "vout": vout}
                )

            # Check if UTXO is locked by another token
            locked_by = self.db.get_utxo_lock(txid, vout)
            if locked_by and locked_by != token_id:
                raise DoubleSpendingError(
                    "UTXO locked by another token",
                    {"txid": txid, "vout": vout, "locked_by": locked_by}
                )

            return True
        except Exception as e:
            logger.error(f"Double spending prevention failed: {str(e)}")
            raise DoubleSpendingError(
                "Double spending prevention failed",
                {"error": str(e)}
            )

    def create_multisig_address(
        self,
        public_keys: List[str],
        required_signatures: int
    ) -> Dict[str, Any]:
        """
        Create a multi-signature address
        """
        try:
            if required_signatures > len(public_keys):
                raise MultiSigError(
                    "Required signatures cannot exceed number of public keys"
                )

            # Create multi-sig address using Bitcoin node
            # This is a placeholder - implement actual Bitcoin multi-sig creation
            multisig_info = {
                "address": "multisig_address",
                "public_keys": public_keys,
                "required_signatures": required_signatures,
                "created_at": datetime.utcnow().isoformat()
            }

            # Store multi-sig information
            self.db.store_multisig_info(multisig_info)
            return multisig_info
        except Exception as e:
            logger.error(f"Multi-signature address creation failed: {str(e)}")
            raise SecurityError(
                "Multi-signature address creation failed",
                {"error": str(e)}
            ) 