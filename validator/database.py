import sqlite3
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from decimal import Decimal
from .schemas import WalletInfo, UTXO, Transaction
import logging
from .electrum import ElectrumClient
import requests
import time
import random

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

    def delete_wallet_data(self, wallet_name: str):
        """Delete all data associated with a wallet"""
        with self._get_connection() as conn:
            try:
                # Start a transaction
                conn.execute("BEGIN TRANSACTION")
                
                # Delete UTXOs
                conn.execute("DELETE FROM utxos WHERE wallet_name = ?", (wallet_name,))
                logging.info(f"Deleted UTXOs for wallet: {wallet_name}")
                
                # Delete transactions
                conn.execute("DELETE FROM transactions WHERE wallet_name = ?", (wallet_name,))
                logging.info(f"Deleted transactions for wallet: {wallet_name}")
                
                # Delete wallet entry
                conn.execute("DELETE FROM wallets WHERE wallet_name = ?", (wallet_name,))
                logging.info(f"Deleted wallet entry: {wallet_name}")
                
                # Commit the transaction
                conn.commit()
                logging.info(f"Successfully deleted all data for wallet: {wallet_name}")
                
            except Exception as e:
                # Rollback in case of error
                conn.rollback()
                logging.error(f"Error deleting wallet data: {str(e)}")
                raise ValueError(f"Failed to delete wallet data: {str(e)}") 

class BitcoinNodeConnector:
    def __init__(self):
        self.api_base_url = "https://blockstream.info/api"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 Bitcoin Explorer',
            'Accept': 'application/json'
        })
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _make_request(self, endpoint: str, params: dict = None) -> Any:
        """Make HTTP request to the API"""
        try:
            url = f"{self.api_base_url}/{endpoint}"
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Handle empty responses (some endpoints return raw data)
            if not response.content:
                return None
                
            # Handle non-JSON responses (like hex data)
            if response.headers.get('content-type', '').startswith('application/json'):
                return response.json()
            return response.text
            
        except requests.RequestException as e:
            self.logger.error(f"API request failed: {str(e)}")
            raise

    def get_transaction_details(self, txid: str) -> Dict[str, Any]:
        """Get detailed information about a transaction"""
        try:
            # Get transaction data
            tx_data = self._make_request(f"tx/{txid}")
            
            # Get transaction status
            tx_status = self._make_request(f"tx/{txid}/status")
            
            # Get transaction hex for additional details
            tx_hex = self._make_request(f"tx/{txid}/hex")
            
            return {
                'txid': txid,
                'version': tx_data.get('version'),
                'size': tx_data.get('size', 0),
                'vsize': tx_data.get('vsize', 0),
                'weight': tx_data.get('weight', 0),
                'locktime': tx_data.get('locktime'),
                'time': tx_status.get('block_time', int(time.time())),
                'confirmations': tx_status.get('confirmed', False),
                'blockheight': tx_status.get('block_height'),
                'blockhash': tx_status.get('block_hash'),
                'fee': tx_data.get('fee', 0),
                'inputs': tx_data.get('vin', []),
                'outputs': tx_data.get('vout', []),
                'hex': tx_hex
            }
        except Exception as e:
            self.logger.error(f"Error getting transaction details: {str(e)}")
            raise

    def get_block_details(self, block_hash: str) -> Dict[str, Any]:
        """Get detailed information about a block"""
        try:
            # Get block data
            block_data = self._make_request(f"block/{block_hash}")
            
            # Get block status
            block_status = self._make_request(f"block/{block_hash}/status")
            
            # Get block header
            block_header = self._make_request(f"block/{block_hash}/header")
            
            return {
                'hash': block_hash,
                'height': block_data.get('height', 0),
                'version': block_data.get('version'),
                'timestamp': block_data.get('timestamp', 0),
                'bits': block_data.get('bits'),
                'nonce': block_data.get('nonce'),
                'merkle_root': block_data.get('merkle_root'),
                'tx_count': block_data.get('tx_count', 0),
                'size': block_data.get('size', 0),
                'weight': block_data.get('weight', 0),
                'prev_block': block_data.get('previousblockhash'),
                'next_block': block_status.get('next_best'),
                'header': block_header,
                'in_best_chain': block_status.get('in_best_chain', True)
            }
        except Exception as e:
            self.logger.error(f"Error getting block details: {str(e)}")
            raise

    def get_block_by_height(self, height: int) -> Dict[str, Any]:
        """Get block details by height"""
        try:
            # Get block hash first
            block_hash = self._make_request(f"block-height/{height}")
            if not block_hash:
                raise Exception(f"Block at height {height} not found")
            
            # Then get block details
            return self.get_block_details(block_hash)
        except Exception as e:
            self.logger.error(f"Error getting block by height: {str(e)}")
            raise

    def get_block_txids(self, block_hash: str, start_index: int = 0) -> List[str]:
        """Get transaction IDs in a block"""
        try:
            return self._make_request(f"block/{block_hash}/txids")
        except Exception as e:
            self.logger.error(f"Error getting block transactions: {str(e)}")
            raise

    def get_block_txs(self, block_hash: str, start_index: int = 0) -> List[Dict[str, Any]]:
        """Get transactions in a block (25 at a time)"""
        try:
            endpoint = f"block/{block_hash}/txs/{start_index}"
            return self._make_request(endpoint)
        except Exception as e:
            self.logger.error(f"Error getting block transactions: {str(e)}")
            raise

    def get_latest_blocks(self, start_height: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get the latest blocks (limited to 5 blocks to avoid rate limiting)"""
        try:
            # Get blocks
            endpoint = "blocks" + (f"/{start_height}" if start_height else "")
            blocks_data = self._make_request(endpoint)
            
            # Limit to 5 blocks
            blocks_data = blocks_data[:5]
            
            blocks = []
            for block in blocks_data:
                try:
                    # Add delay between requests to avoid rate limiting
                    time.sleep(0.5)  # 500ms delay between requests
                    block_details = self.get_block_details(block['id'])
                    blocks.append(block_details)
                except Exception as e:
                    self.logger.error(f"Error getting block details: {str(e)}")
                    continue
            
            return {'blocks': blocks}
        except Exception as e:
            self.logger.error(f"Error getting latest blocks: {str(e)}")
            raise

    def get_mempool_info(self) -> Dict[str, Any]:
        """Get information about the mempool"""
        try:
            mempool_data = self._make_request("mempool")
            fee_data = self._make_request("fee-estimates")
            
            return {
                'count': mempool_data.get('count', 0),
                'vsize': mempool_data.get('vsize', 0),
                'total_fee': mempool_data.get('total_fee', 0),
                'fee_histogram': mempool_data.get('fee_histogram', []),
                'fee_estimates': fee_data
            }
        except Exception as e:
            self.logger.error(f"Error getting mempool info: {str(e)}")
            raise

    def get_mempool_txids(self) -> List[str]:
        """Get all transaction IDs in the mempool"""
        try:
            return self._make_request("mempool/txids")
        except Exception as e:
            self.logger.error(f"Error getting mempool txids: {str(e)}")
            raise

    def get_mempool_recent(self) -> List[Dict[str, Any]]:
        """Get recent mempool transactions"""
        try:
            return self._make_request("mempool/recent")
        except Exception as e:
            self.logger.error(f"Error getting recent mempool transactions: {str(e)}")
            raise

    def get_network_info(self) -> Dict[str, Any]:
        """Get network information"""
        try:
            # Get latest block height
            tip_height = self._make_request("blocks/tip/height")
            
            # Get latest block hash
            tip_hash = self._make_request("blocks/tip/hash")
            
            # Get block header only instead of full details
            block_header = self._make_request(f"block/{tip_hash}/header")
            
            # Get mempool info
            mempool = self.get_mempool_info()
            
            # Calculate hashrate (rough estimate based on difficulty)
            # Extract difficulty from block header
            difficulty_bits = int(block_header[-8:], 16)  # Last 4 bytes of header contain difficulty bits
            hashrate = difficulty_bits * 2**32 / 600  # Average block time is 600 seconds
            
            return {
                'height': int(tip_height),
                'best_block_hash': tip_hash,
                'difficulty': difficulty_bits,
                'hashrate': hashrate,
                'mempool_size': mempool['count'],
                'mempool_bytes': mempool['vsize'],
                'mempool_fee': mempool['total_fee'],
                'fee_estimates': mempool['fee_estimates']
            }
        except Exception as e:
            self.logger.error(f"Error getting network info: {str(e)}")
            raise 