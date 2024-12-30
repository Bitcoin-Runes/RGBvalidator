from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, validator
from enum import Enum
from decimal import Decimal
from dataclasses import dataclass

class TokenSchemaVersion(str, Enum):
    V1 = "1.0.0"
    V2 = "2.0.0"

class BaseTokenSchema(BaseModel):
    schema_version: TokenSchemaVersion = Field(default=TokenSchemaVersion.V1)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    utxo: Dict[str, Any] = Field(..., description="UTXO reference for token validation")
    signature: str = Field(..., description="Signature of the token data")
    owner_address: str = Field(..., description="Bitcoin address of the token owner")
    created_at: str = Field(..., description="Token creation timestamp")
    metadata: Dict[str, Any] = Field(default={}, description="Additional token metadata")

    @validator('utxo')
    def validate_utxo(cls, v):
        required_fields = ['txid', 'vout', 'amount', 'script_pubkey']
        if not all(field in v for field in required_fields):
            raise ValueError(f"UTXO must contain all required fields: {required_fields}")
        return v

class FungibleTokenSchema(BaseTokenSchema):
    token_type: str = Field(default="fungible", const=True)
    total_supply: int = Field(..., gt=0)
    decimals: int = Field(default=18, ge=0, le=18)
    current_supply: int = Field(..., ge=0)
    is_mintable: bool = Field(default=False)
    is_burnable: bool = Field(default=False)

class NFTAttributeSchema(BaseModel):
    trait_type: str = Field(..., min_length=1)
    value: Any = Field(...)
    display_type: str = Field(default=None)

class NonFungibleTokenSchema(BaseTokenSchema):
    token_type: str = Field(default="non_fungible", const=True)
    token_id: str = Field(..., min_length=1)
    metadata_uri: str = Field(default=None)
    attributes: list[NFTAttributeSchema] = Field(default=[])
    content_hash: str = Field(default=None, description="Hash of the NFT content")
    is_transferable: bool = Field(default=True)

class TokenTransferSchema(BaseModel):
    token_id: str = Field(..., description="Token identifier")
    from_address: str = Field(..., description="Sender's Bitcoin address")
    to_address: str = Field(..., description="Recipient's Bitcoin address")
    amount: int = Field(..., gt=0, description="Amount to transfer (1 for NFTs)")
    utxo: Dict[str, Any] = Field(..., description="UTXO reference for transfer validation")
    signature: str = Field(..., description="Signature of the transfer data")

class TokenBurnSchema(BaseModel):
    token_id: str = Field(..., description="Token identifier")
    owner_address: str = Field(..., description="Token owner's Bitcoin address")
    amount: int = Field(..., gt=0, description="Amount to burn (1 for NFTs)")
    utxo: Dict[str, Any] = Field(..., description="UTXO reference for burn validation")
    signature: str = Field(..., description="Signature of the burn data")

@dataclass
class UTXO:
    txid: str
    vout: int
    amount: Decimal
    address: str
    wallet_name: str
    frozen: bool = False
    memo: Optional[str] = None
    confirmations: int = 0
    is_coinbase: bool = False

@dataclass
class Transaction:
    txid: str
    timestamp: int
    amount: Decimal
    fee: Decimal
    from_addresses: List[str]
    to_addresses: List[str]
    wallet_name: str
    change_address: str
    status: str
    memo: Optional[str] = None

@dataclass
class WalletInfo:
    wallet_name: str
    address: str
    balance: Decimal

def validate_token_schema(token_data: Dict[str, Any], token_type: str) -> bool:
    """
    Validate token data against the appropriate schema
    """
    try:
        if token_type == "fungible":
            FungibleTokenSchema(**token_data)
        elif token_type == "non_fungible":
            NonFungibleTokenSchema(**token_data)
        else:
            raise ValueError(f"Invalid token type: {token_type}")
        return True
    except Exception as e:
        raise ValueError(f"Schema validation failed: {str(e)}")

def validate_transfer_schema(transfer_data: Dict[str, Any]) -> bool:
    """
    Validate token transfer data
    """
    try:
        TokenTransferSchema(**transfer_data)
        return True
    except Exception as e:
        raise ValueError(f"Transfer validation failed: {str(e)}")

def validate_burn_schema(burn_data: Dict[str, Any]) -> bool:
    """
    Validate token burn data
    """
    try:
        TokenBurnSchema(**burn_data)
        return True
    except Exception as e:
        raise ValueError(f"Burn validation failed: {str(e)}") 