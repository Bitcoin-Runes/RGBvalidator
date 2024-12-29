from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum

class TokenType(str, Enum):
    FUNGIBLE = "fungible"
    NON_FUNGIBLE = "non_fungible"

class UTXOReference(BaseModel):
    txid: str
    vout: int
    amount: float

class WalletInfo(BaseModel):
    wallet_name: str
    address: str
    balance: Optional[float] = 0.0

class BaseToken(BaseModel):
    name: str
    description: Optional[str] = None
    token_type: TokenType
    utxo_ref: UTXOReference
    signature: Optional[str] = None
    wallet_name: str

class FungibleToken(BaseToken):
    total_supply: int
    decimals: int = 18

class NFTAttribute(BaseModel):
    trait_type: str
    value: str

class NonFungibleToken(BaseToken):
    token_id: str
    attributes: Optional[List[NFTAttribute]] = None
    metadata_uri: Optional[str] = None

class WalletCreate(BaseModel):
    wallet_name: str = Field(..., description="Name for the new wallet") 