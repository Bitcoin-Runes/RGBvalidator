from typing import List, Dict, Union
from pydantic import BaseModel
import asyncio
import json
from pathlib import Path

from .models import FungibleToken, NonFungibleToken, TokenType
from .database import Database
from .bitcoin_client import bitcoin_client
from .crypto import signature_validator
from .logging_config import logger

class BatchTokenOperation(BaseModel):
    wallet_name: str
    tokens: List[Dict]

class BatchProcessor:
    def __init__(self):
        self.db = Database()

    async def process_batch(self, operation: BatchTokenOperation) -> Dict:
        """Process a batch of token operations"""
        results = {
            "successful": [],
            "failed": []
        }

        # Verify wallet exists
        if not self.db.get_wallet(operation.wallet_name):
            raise ValueError(f"Wallet not found: {operation.wallet_name}")

        # Get available UTXOs
        utxos = bitcoin_client.get_utxos(operation.wallet_name)
        if not utxos:
            raise ValueError(f"No UTXOs available for wallet: {operation.wallet_name}")

        # Process tokens in parallel
        tasks = []
        for token_data in operation.tokens:
            if len(utxos) == 0:
                results["failed"].append({
                    "token": token_data,
                    "error": "No UTXO available"
                })
                continue

            # Assign UTXO to token
            utxo = utxos.pop(0)
            token_data["utxo_ref"] = {
                "txid": utxo["txid"],
                "vout": utxo["vout"],
                "amount": utxo["amount"]
            }
            token_data["wallet_name"] = operation.wallet_name

            # Create task for token processing
            tasks.append(self._process_token(token_data, results))

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)
        return results

    async def _process_token(self, token_data: Dict, results: Dict):
        """Process a single token in the batch"""
        try:
            # Determine token type and create appropriate object
            token_type = token_data.get("token_type", "").lower()
            if token_type == TokenType.FUNGIBLE:
                token = FungibleToken(**token_data)
            elif token_type == TokenType.NON_FUNGIBLE:
                token = NonFungibleToken(**token_data)
            else:
                raise ValueError(f"Invalid token type: {token_type}")

            # Verify UTXO
            if not bitcoin_client.verify_utxo(
                token.utxo_ref.txid,
                token.utxo_ref.vout
            ):
                raise ValueError("Invalid UTXO")

            # Create signature
            token.signature = signature_validator.create_token_signature(
                token,
                token.wallet_name
            )

            # Store token
            self.db.store_token(token)
            results["successful"].append({
                "token": token_data,
                "utxo": token.utxo_ref.dict()
            })

        except Exception as e:
            logger.error(f"Error processing token: {str(e)}")
            results["failed"].append({
                "token": token_data,
                "error": str(e)
            })

    def load_batch_file(self, file_path: Union[str, Path]) -> BatchTokenOperation:
        """Load batch operations from a JSON file"""
        try:
            with open(file_path) as f:
                data = json.load(f)
                return BatchTokenOperation(**data)
        except Exception as e:
            raise ValueError(f"Error loading batch file: {str(e)}")

# Create global instance
batch_processor = BatchProcessor() 