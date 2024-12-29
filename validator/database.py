import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Union, List, Optional

from .models import FungibleToken, NonFungibleToken, WalletInfo
from .config import get_settings

settings = get_settings()

class Database:
    def __init__(self, db_path: str = settings.DATABASE_URL):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            # Create tokens table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token_type TEXT NOT NULL,
                    utxo_txid TEXT NOT NULL,
                    utxo_vout INTEGER NOT NULL,
                    utxo_amount REAL NOT NULL,
                    wallet_name TEXT NOT NULL,
                    data JSON NOT NULL,
                    signature TEXT,
                    UNIQUE(utxo_txid, utxo_vout)
                )
            """)
            
            # Create wallets table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    wallet_name TEXT PRIMARY KEY,
                    address TEXT NOT NULL,
                    balance REAL DEFAULT 0.0
                )
            """)

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def store_token(self, token: Union[FungibleToken, NonFungibleToken]):
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO tokens 
                   (token_type, utxo_txid, utxo_vout, utxo_amount, wallet_name, data, signature) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    token.token_type,
                    token.utxo_ref.txid,
                    token.utxo_ref.vout,
                    token.utxo_ref.amount,
                    token.wallet_name,
                    json.dumps(token.dict()),
                    token.signature
                )
            )
            conn.commit()

    def get_token_by_utxo(self, txid: str, vout: int) -> Union[FungibleToken, NonFungibleToken, None]:
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT * FROM tokens WHERE utxo_txid = ? AND utxo_vout = ?",
                (txid, vout)
            ).fetchone()
            
            if not result:
                return None

            data = json.loads(result["data"])
            if data["token_type"] == "fungible":
                return FungibleToken(**data)
            return NonFungibleToken(**data)

    def store_wallet(self, wallet_info: WalletInfo):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO wallets (wallet_name, address, balance) VALUES (?, ?, ?)",
                (wallet_info.wallet_name, wallet_info.address, wallet_info.balance)
            )
            conn.commit()

    def get_wallet(self, wallet_name: str) -> Optional[WalletInfo]:
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT * FROM wallets WHERE wallet_name = ?",
                (wallet_name,)
            ).fetchone()
            
            if not result:
                return None
                
            return WalletInfo(
                wallet_name=result["wallet_name"],
                address=result["address"],
                balance=result["balance"]
            )

    def update_wallet_balance(self, wallet_name: str, balance: float):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE wallets SET balance = ? WHERE wallet_name = ?",
                (balance, wallet_name)
            )
            conn.commit()

    def list_wallets(self) -> List[WalletInfo]:
        with self._get_connection() as conn:
            results = conn.execute("SELECT * FROM wallets").fetchall()
            return [
                WalletInfo(
                    wallet_name=row["wallet_name"],
                    address=row["address"],
                    balance=row["balance"]
                )
                for row in results
            ] 