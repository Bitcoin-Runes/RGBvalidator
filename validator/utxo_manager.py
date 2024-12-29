from typing import Dict, List, Optional, Any
from datetime import datetime
import sqlite3
from .bitcoin_client import BitcoinClient
from .crypto import SignatureValidator
from .logging_config import logger

class UTXOState:
    UNSPENT = "unspent"
    LOCKED = "locked"
    SPENT = "spent"
    INVALID = "invalid"

class UTXOManager:
    def __init__(self, db_path: str, bitcoin_client: BitcoinClient):
        self.db_path = db_path
        self.bitcoin_client = bitcoin_client
        self.signature_validator = SignatureValidator()
        self._init_db()

    def _init_db(self):
        """Initialize the UTXO tracking database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS utxo_tracking (
                    txid TEXT,
                    vout INTEGER,
                    amount REAL,
                    script_pubkey TEXT,
                    owner_address TEXT,
                    state TEXT,
                    locked_at TIMESTAMP,
                    locked_by TEXT,
                    spent_at TIMESTAMP,
                    spent_txid TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (txid, vout)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS utxo_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    txid TEXT,
                    vout INTEGER,
                    previous_state TEXT,
                    new_state TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    changed_by TEXT,
                    reason TEXT
                )
            """)

    def verify_utxo(self, txid: str, vout: int) -> bool:
        """Verify if a UTXO exists and is valid"""
        try:
            utxo = self.bitcoin_client.get_utxo(txid, vout)
            if not utxo:
                return False
            return True
        except Exception as e:
            logger.error(f"Error verifying UTXO: {str(e)}")
            return False

    def lock_utxo(self, txid: str, vout: int, owner_address: str, token_id: str) -> bool:
        """Lock a UTXO for token creation/transfer"""
        try:
            if not self.verify_utxo(txid, vout):
                return False

            with sqlite3.connect(self.db_path) as conn:
                # Check current state
                cursor = conn.execute(
                    "SELECT state FROM utxo_tracking WHERE txid = ? AND vout = ?",
                    (txid, vout)
                )
                result = cursor.fetchone()
                
                if result and result[0] != UTXOState.UNSPENT:
                    return False

                # Lock the UTXO
                now = datetime.utcnow()
                conn.execute("""
                    INSERT OR REPLACE INTO utxo_tracking 
                    (txid, vout, amount, script_pubkey, owner_address, state, locked_at, locked_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (txid, vout, utxo['amount'], utxo['script_pubkey'], 
                     owner_address, UTXOState.LOCKED, now, token_id))

                # Record history
                conn.execute("""
                    INSERT INTO utxo_history 
                    (txid, vout, previous_state, new_state, changed_by, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (txid, vout, UTXOState.UNSPENT, UTXOState.LOCKED, 
                     token_id, "Token creation/transfer"))

                return True
        except Exception as e:
            logger.error(f"Error locking UTXO: {str(e)}")
            return False

    def verify_ownership(self, txid: str, vout: int, address: str, signature: str) -> bool:
        """Verify UTXO ownership using signature"""
        try:
            utxo = self.bitcoin_client.get_utxo(txid, vout)
            if not utxo:
                return False

            # Verify the signature matches the address and UTXO
            message = f"{txid}:{vout}"
            return self.signature_validator.verify_signature(message, signature, address)
        except Exception as e:
            logger.error(f"Error verifying ownership: {str(e)}")
            return False

    def mark_utxo_spent(self, txid: str, vout: int, spent_txid: str) -> bool:
        """Mark a UTXO as spent"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                now = datetime.utcnow()
                conn.execute("""
                    UPDATE utxo_tracking 
                    SET state = ?, spent_at = ?, spent_txid = ?, updated_at = ?
                    WHERE txid = ? AND vout = ?
                """, (UTXOState.SPENT, now, spent_txid, now, txid, vout))

                conn.execute("""
                    INSERT INTO utxo_history 
                    (txid, vout, previous_state, new_state, changed_by, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (txid, vout, UTXOState.LOCKED, UTXOState.SPENT, 
                     spent_txid, "Token spent"))

                return True
        except Exception as e:
            logger.error(f"Error marking UTXO as spent: {str(e)}")
            return False

    def get_utxo_state(self, txid: str, vout: int) -> Optional[str]:
        """Get the current state of a UTXO"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT state FROM utxo_tracking WHERE txid = ? AND vout = ?",
                    (txid, vout)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting UTXO state: {str(e)}")
            return None

    def get_utxo_history(self, txid: str, vout: int) -> List[Dict[str, Any]]:
        """Get the history of a UTXO"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT * FROM utxo_history 
                    WHERE txid = ? AND vout = ?
                    ORDER BY changed_at DESC
                """, (txid, vout))
                
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting UTXO history: {str(e)}")
            return []

    def select_utxos(self, address: str, amount: float) -> List[Dict[str, Any]]:
        """Select appropriate UTXOs for a transaction"""
        try:
            utxos = self.bitcoin_client.list_utxos(address)
            selected = []
            total = 0.0

            # Simple UTXO selection algorithm (can be improved)
            for utxo in sorted(utxos, key=lambda x: x['amount']):
                if self.get_utxo_state(utxo['txid'], utxo['vout']) == UTXOState.UNSPENT:
                    selected.append(utxo)
                    total += utxo['amount']
                    if total >= amount:
                        break

            return selected if total >= amount else []
        except Exception as e:
            logger.error(f"Error selecting UTXOs: {str(e)}")
            return [] 