import sqlite3
import json
from typing import List, Optional, Dict
from pathlib import Path
from decimal import Decimal
from .schemas import WalletInfo, UTXO, Transaction
import logging

class Database:
    def __init__(self, db_path: str = "data/wallet.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database with required tables and handle schema updates"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_connection() as conn:
            # Create initial tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    wallet_name TEXT PRIMARY KEY,
                    address TEXT NOT NULL,
                    balance REAL DEFAULT 0
                )
            """)
            
            # Create UTXO table with basic structure
            conn.execute("""
                CREATE TABLE IF NOT EXISTS utxos (
                    txid TEXT,
                    vout INTEGER,
                    amount REAL,
                    address TEXT,
                    frozen BOOLEAN DEFAULT 0,
                    memo TEXT,
                    wallet_name TEXT,
                    PRIMARY KEY (txid, vout),
                    FOREIGN KEY (wallet_name) REFERENCES wallets(wallet_name)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    txid TEXT PRIMARY KEY,
                    timestamp INTEGER,
                    amount REAL,
                    fee REAL,
                    memo TEXT,
                    from_addresses TEXT,  -- JSON array
                    to_addresses TEXT,    -- JSON array
                    wallet_name TEXT,
                    change_address TEXT,
                    status TEXT,
                    FOREIGN KEY (wallet_name) REFERENCES wallets(wallet_name)
                )
            """)
            
            # Check and add new columns if they don't exist
            try:
                # Check if confirmations column exists
                conn.execute("SELECT confirmations FROM utxos LIMIT 1")
            except sqlite3.OperationalError:
                logging.info("Adding confirmations column to utxos table")
                conn.execute("ALTER TABLE utxos ADD COLUMN confirmations INTEGER DEFAULT 0")
            
            try:
                # Check if is_coinbase column exists
                conn.execute("SELECT is_coinbase FROM utxos LIMIT 1")
            except sqlite3.OperationalError:
                logging.info("Adding is_coinbase column to utxos table")
                conn.execute("ALTER TABLE utxos ADD COLUMN is_coinbase BOOLEAN DEFAULT 0")
            
            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def store_utxo(self, utxo: UTXO):
        """Store or update a UTXO"""
        with self._get_connection() as conn:
            # Check if UTXO already exists and is frozen
            existing = conn.execute("""
                SELECT frozen FROM utxos 
                WHERE txid = ? AND vout = ? AND wallet_name = ?
            """, (utxo.txid, utxo.vout, utxo.wallet_name)).fetchone()

            if existing and existing[0] and not utxo.frozen:
                # Don't update frozen UTXOs unless explicitly freezing
                logging.info(f"Skipping update of frozen UTXO: {utxo.txid}:{utxo.vout}")
                return

            conn.execute("""
                INSERT OR REPLACE INTO utxos 
                (txid, vout, amount, address, frozen, memo, wallet_name, confirmations, is_coinbase)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                utxo.txid,
                utxo.vout,
                float(utxo.amount),
                utxo.address,
                utxo.frozen,
                utxo.memo,
                utxo.wallet_name,
                getattr(utxo, 'confirmations', 0),
                getattr(utxo, 'is_coinbase', False)
            ))
            conn.commit()
            logging.info(f"{'Updated' if existing else 'Stored'} UTXO: {utxo.txid}:{utxo.vout} (frozen: {utxo.frozen})")

    def get_utxos(self, wallet_name: str, include_frozen: bool = False) -> List[UTXO]:
        """Get all UTXOs for a wallet"""
        with self._get_connection() as conn:
            query = """
                SELECT * FROM utxos 
                WHERE wallet_name = ?
            """
            if not include_frozen:
                query += " AND frozen = 0"
            
            results = conn.execute(query, (wallet_name,)).fetchall()
            utxos = []
            for row in results:
                try:
                    utxo = UTXO(
                        txid=row['txid'],
                        vout=row['vout'],
                        amount=Decimal(str(row['amount'])),
                        address=row['address'],
                        frozen=bool(row['frozen']),
                        memo=row['memo'],
                        wallet_name=row['wallet_name'],
                        confirmations=row['confirmations'] if 'confirmations' in row.keys() else 0,
                        is_coinbase=bool(row['is_coinbase']) if 'is_coinbase' in row.keys() else False
                    )
                    utxos.append(utxo)
                except Exception as e:
                    logging.error(f"Error creating UTXO object from row: {str(e)}")
                    continue
            
            logging.info(f"Retrieved {len(utxos)} UTXOs for wallet {wallet_name} (include_frozen: {include_frozen})")
            return utxos

    def freeze_utxo(self, txid: str, vout: int, memo: Optional[str] = None):
        """Freeze a UTXO"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE utxos 
                SET frozen = 1, memo = COALESCE(?, memo)
                WHERE txid = ? AND vout = ?
            """, (memo, txid, vout))
            conn.commit()
            logging.info(f"Froze UTXO: {txid}:{vout}")

    def unfreeze_utxo(self, txid: str, vout: int):
        """Unfreeze a UTXO"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE utxos 
                SET frozen = 0
                WHERE txid = ? AND vout = ?
            """, (txid, vout))
            conn.commit()
            logging.info(f"Unfroze UTXO: {txid}:{vout}")

    def store_transaction(self, tx: Transaction):
        """Store a transaction"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO transactions 
                (txid, timestamp, amount, fee, memo, from_addresses, to_addresses, 
                 wallet_name, change_address, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx.txid,
                tx.timestamp,
                float(tx.amount),
                float(tx.fee),
                tx.memo,
                json.dumps(tx.from_addresses),
                json.dumps(tx.to_addresses),
                tx.wallet_name,
                tx.change_address,
                tx.status
            ))
            conn.commit()

    def get_transactions(self, wallet_name: str) -> List[Transaction]:
        """Get all transactions for a wallet"""
        with self._get_connection() as conn:
            results = conn.execute("""
                SELECT * FROM transactions 
                WHERE wallet_name = ?
                ORDER BY timestamp DESC
            """, (wallet_name,)).fetchall()
            
            return [Transaction(
                txid=row['txid'],
                timestamp=row['timestamp'],
                amount=Decimal(str(row['amount'])),
                fee=Decimal(str(row['fee'])),
                memo=row['memo'],
                from_addresses=json.loads(row['from_addresses']),
                to_addresses=json.loads(row['to_addresses']),
                wallet_name=row['wallet_name'],
                change_address=row['change_address'],
                status=row['status']
            ) for row in results]

    def store_wallet(self, wallet_info: WalletInfo):
        """Store or update wallet information"""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO wallets (wallet_name, address, balance)
                VALUES (?, ?, ?)
            """, (
                wallet_info.wallet_name,
                wallet_info.address,
                float(wallet_info.balance)
            ))
            conn.commit()

    def get_wallet(self, wallet_name: str) -> Optional[WalletInfo]:
        """Get wallet information"""
        with self._get_connection() as conn:
            result = conn.execute("""
                SELECT * FROM wallets WHERE wallet_name = ?
            """, (wallet_name,)).fetchone()
            
            if not result:
                return None
            
            return WalletInfo(
                wallet_name=result['wallet_name'],
                address=result['address'],
                balance=Decimal(str(result['balance']))
            )

    def update_wallet_balance(self, wallet_name: str, balance: Decimal):
        """Update wallet balance"""
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE wallets 
                SET balance = ?
                WHERE wallet_name = ?
            """, (float(balance), wallet_name))
            conn.commit()

    def list_wallets(self) -> List[WalletInfo]:
        """List all wallets"""
        with self._get_connection() as conn:
            results = conn.execute("SELECT * FROM wallets").fetchall()
            return [WalletInfo(
                wallet_name=row['wallet_name'],
                address=row['address'],
                balance=Decimal(str(row['balance']))
            ) for row in results]

    def remove_utxo(self, txid: str, vout: int):
        """Remove a UTXO from the database"""
        with self._get_connection() as conn:
            # Check if UTXO is frozen before removing
            frozen = conn.execute("""
                SELECT frozen FROM utxos 
                WHERE txid = ? AND vout = ?
            """, (txid, vout)).fetchone()

            if frozen and frozen[0]:
                logging.warning(f"Attempted to remove frozen UTXO: {txid}:{vout}")
                return

            conn.execute("""
                DELETE FROM utxos 
                WHERE txid = ? AND vout = ?
            """, (txid, vout))
            conn.commit()
            logging.info(f"Removed UTXO: {txid}:{vout}")

    def clear_utxos(self, wallet_name: str):
        """Clear all unfrozen UTXOs for a wallet"""
        with self._get_connection() as conn:
            # Only clear unfrozen UTXOs
            conn.execute("""
                DELETE FROM utxos 
                WHERE wallet_name = ? AND frozen = 0
            """, (wallet_name,))
            conn.commit()
            logging.info(f"Cleared unfrozen UTXOs for wallet: {wallet_name}") 