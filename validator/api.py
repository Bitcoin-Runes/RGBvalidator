from fastapi import FastAPI, HTTPException, Depends
from typing import List

from .database import Database
from .models import (
    FungibleToken, NonFungibleToken, WalletInfo,
    WalletCreate, UTXOReference
)
from .bitcoin_client import bitcoin_client
from .config import get_settings

settings = get_settings()
app = FastAPI(title="Token Validator API")
db = Database()

# Wallet Management Endpoints
@app.post("/wallets", response_model=WalletInfo)
async def create_wallet(wallet_create: WalletCreate):
    """Create a new Bitcoin wallet"""
    try:
        # Create wallet in Bitcoin node
        wallet_info = bitcoin_client.create_wallet(wallet_create.wallet_name)
        
        # Store wallet info in database
        wallet = WalletInfo(
            wallet_name=wallet_info["wallet_name"],
            address=wallet_info["address"],
            balance=0.0
        )
        db.store_wallet(wallet)
        return wallet
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/wallets/{wallet_name}", response_model=WalletInfo)
async def get_wallet(wallet_name: str):
    """Get wallet information"""
    wallet = db.get_wallet(wallet_name)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    # Update balance from Bitcoin node
    try:
        balance = bitcoin_client.get_wallet_balance(wallet_name)
        db.update_wallet_balance(wallet_name, balance)
        wallet.balance = balance
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return wallet

@app.get("/wallets/{wallet_name}/utxos", response_model=List[UTXOReference])
async def get_wallet_utxos(wallet_name: str):
    """Get list of UTXOs for a wallet"""
    try:
        utxos = bitcoin_client.get_utxos(wallet_name)
        return [
            UTXOReference(
                txid=utxo["txid"],
                vout=utxo["vout"],
                amount=utxo["amount"]
            )
            for utxo in utxos
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/wallets/{wallet_name}/address")
async def get_wallet_address(wallet_name: str):
    """Get a new address for the wallet"""
    try:
        address = bitcoin_client.get_wallet_address(wallet_name)
        return {"address": address}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Token Management Endpoints
@app.post("/tokens/fungible")
async def create_fungible_token(token: FungibleToken):
    """Create a new fungible token"""
    try:
        # Verify UTXO exists
        if not bitcoin_client.verify_utxo(token.utxo_ref.txid, token.utxo_ref.vout):
            raise HTTPException(status_code=400, detail="Invalid UTXO")
        
        # Verify wallet exists
        if not db.get_wallet(token.wallet_name):
            raise HTTPException(status_code=400, detail="Wallet not found")
        
        db.store_token(token)
        return {"status": "success", "message": f"Token stored with UTXO: {token.utxo_ref.txid}:{token.utxo_ref.vout}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/tokens/non-fungible")
async def create_non_fungible_token(token: NonFungibleToken):
    """Create a new non-fungible token"""
    try:
        # Verify UTXO exists
        if not bitcoin_client.verify_utxo(token.utxo_ref.txid, token.utxo_ref.vout):
            raise HTTPException(status_code=400, detail="Invalid UTXO")
        
        # Verify wallet exists
        if not db.get_wallet(token.wallet_name):
            raise HTTPException(status_code=400, detail="Wallet not found")
        
        db.store_token(token)
        return {"status": "success", "message": f"Token stored with UTXO: {token.utxo_ref.txid}:{token.utxo_ref.vout}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/tokens/{txid}/{vout}")
async def get_token(txid: str, vout: int):
    """Get a token by its UTXO reference"""
    token = db.get_token_by_utxo(txid, vout)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token 