import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from validator.api import app
from validator.models import (
    TokenType, FungibleToken, NonFungibleToken,
    UTXOReference, WalletInfo
)
from validator.database import Database
from validator.crypto import SignatureValidator

@pytest.fixture
def test_client():
    return TestClient(app)

@pytest.fixture
def mock_bitcoin_client():
    with patch('validator.bitcoin_client.BitcoinClient') as mock:
        yield mock

@pytest.fixture
def mock_signature_validator():
    with patch('validator.crypto.SignatureValidator') as mock:
        yield mock

@pytest.fixture
def test_wallet():
    return WalletInfo(
        wallet_name="test_wallet",
        address="test_address",
        balance=1.0
    )

@pytest.fixture
def test_utxo():
    return UTXOReference(
        txid="test_txid",
        vout=0,
        amount=1.0
    )

class TestWalletAPI:
    def test_create_wallet(self, test_client, mock_bitcoin_client):
        mock_bitcoin_client.create_wallet.return_value = {
            "wallet_name": "test_wallet",
            "address": "test_address",
            "status": "created"
        }
        
        response = test_client.post(
            "/wallets",
            json={"wallet_name": "test_wallet"}
        )
        
        assert response.status_code == 200
        assert response.json()["wallet_name"] == "test_wallet"
    
    def test_get_wallet(self, test_client, mock_bitcoin_client, test_wallet):
        mock_bitcoin_client.get_wallet_balance.return_value = 1.0
        
        response = test_client.get("/wallets/test_wallet")
        
        assert response.status_code == 200
        assert response.json()["wallet_name"] == "test_wallet"

class TestTokenAPI:
    def test_create_fungible_token(
        self, test_client, mock_bitcoin_client,
        mock_signature_validator, test_wallet, test_utxo
    ):
        mock_bitcoin_client.verify_utxo.return_value = True
        mock_signature_validator.create_token_signature.return_value = "test_signature"
        
        token_data = {
            "name": "Test Token",
            "description": "Test Description",
            "token_type": "fungible",
            "wallet_name": "test_wallet",
            "utxo_ref": test_utxo.dict(),
            "total_supply": 1000000,
            "decimals": 18
        }
        
        response = test_client.post(
            "/tokens/fungible",
            json=token_data
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"
    
    def test_create_nft(
        self, test_client, mock_bitcoin_client,
        mock_signature_validator, test_wallet, test_utxo
    ):
        mock_bitcoin_client.verify_utxo.return_value = True
        mock_signature_validator.create_token_signature.return_value = "test_signature"
        
        token_data = {
            "name": "Test NFT",
            "description": "Test Description",
            "token_type": "non_fungible",
            "wallet_name": "test_wallet",
            "utxo_ref": test_utxo.dict(),
            "token_id": "nft1",
            "metadata_uri": "ipfs://test"
        }
        
        response = test_client.post(
            "/tokens/non-fungible",
            json=token_data
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "success"

class TestSignatureValidation:
    def test_create_signature(self, mock_signature_validator, test_utxo):
        token = FungibleToken(
            name="Test Token",
            token_type=TokenType.FUNGIBLE,
            wallet_name="test_wallet",
            utxo_ref=test_utxo,
            total_supply=1000000
        )
        
        signature = mock_signature_validator.create_token_signature(
            token, "test_wallet"
        )
        assert signature == "test_signature"
    
    def test_verify_signature(self, mock_signature_validator, test_utxo):
        token = FungibleToken(
            name="Test Token",
            token_type=TokenType.FUNGIBLE,
            wallet_name="test_wallet",
            utxo_ref=test_utxo,
            total_supply=1000000,
            signature="test_signature"
        )
        
        is_valid = mock_signature_validator.verify_token_signature(token)
        assert is_valid is True 