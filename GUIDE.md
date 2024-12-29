# Token Validator Guide

This guide explains how to use the Token Validator's CLI and API interfaces.

## Prerequisites

1. Python 3.8 or higher
2. Access to a Bitcoin node (default: local node at 127.0.0.1:18443)
3. Required Python packages (install via `pip install -r requirements.txt`)

## Configuration

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Update the `.env` file with your Bitcoin node credentials:
   ```env
   BITCOIN_RPC_HOST=127.0.0.1
   BITCOIN_RPC_PORT=18443
   BITCOIN_RPC_USER=your_rpc_username
   BITCOIN_RPC_PASSWORD=your_rpc_password
   ```

## Using the CLI

The CLI provides two main command groups: `wallet` and `token`.

### Wallet Management

1. Create a new wallet:
   ```bash
   python -m validator wallet create my_wallet
   ```

2. Get wallet information:
   ```bash
   python -m validator wallet info my_wallet
   ```

3. List all wallets:
   ```bash
   python -m validator wallet list
   ```

4. Get a new wallet address:
   ```bash
   python -m validator wallet address my_wallet
   ```

5. List wallet UTXOs:
   ```bash
   python -m validator wallet utxos my_wallet
   ```

### Token Management

1. Create a fungible token:
   ```bash
   python -m validator token create-fungible \
       --name "My Token" \
       --description "My first fungible token" \
       --wallet-name my_wallet \
       --txid abc123... \
       --vout 0 \
       --amount 1.0 \
       --total-supply 1000000 \
       --decimals 18
   ```

2. Create a non-fungible token:
   ```bash
   python -m validator token create-nft \
       --name "My NFT" \
       --description "My first NFT" \
       --wallet-name my_wallet \
       --txid abc123... \
       --vout 0 \
       --amount 1.0 \
       --token-id "nft1" \
       --metadata-uri "ipfs://..." \
       --attributes-file metadata.json
   ```

3. Get token information:
   ```bash
   python -m validator token get abc123... 0
   ```

## Using the API

The API server provides RESTful endpoints for all validator operations.

### Starting the API Server

```bash
python -m validator serve
```

The server will start at `http://127.0.0.1:8000` by default.

### API Endpoints

#### Wallet Management

1. Create a new wallet:
   ```bash
   curl -X POST "http://localhost:8000/wallets" \
       -H "Content-Type: application/json" \
       -d '{"wallet_name": "my_wallet"}'
   ```

2. Get wallet information:
   ```bash
   curl "http://localhost:8000/wallets/my_wallet"
   ```

3. Get wallet address:
   ```bash
   curl "http://localhost:8000/wallets/my_wallet/address"
   ```

4. Get wallet UTXOs:
   ```bash
   curl "http://localhost:8000/wallets/my_wallet/utxos"
   ```

#### Token Management

1. Create a fungible token:
   ```bash
   curl -X POST "http://localhost:8000/tokens/fungible" \
       -H "Content-Type: application/json" \
       -d '{
           "name": "My Token",
           "description": "My first fungible token",
           "token_type": "fungible",
           "wallet_name": "my_wallet",
           "utxo_ref": {
               "txid": "abc123...",
               "vout": 0,
               "amount": 1.0
           },
           "total_supply": 1000000,
           "decimals": 18
       }'
   ```

2. Create a non-fungible token:
   ```bash
   curl -X POST "http://localhost:8000/tokens/non-fungible" \
       -H "Content-Type: application/json" \
       -d '{
           "name": "My NFT",
           "description": "My first NFT",
           "token_type": "non_fungible",
           "wallet_name": "my_wallet",
           "utxo_ref": {
               "txid": "abc123...",
               "vout": 0,
               "amount": 1.0
           },
           "token_id": "nft1",
           "metadata_uri": "ipfs://..."
       }'
   ```

3. Get token information:
   ```bash
   curl "http://localhost:8000/tokens/abc123.../0"
   ```

## Working with Bitcoin Node

1. After creating a wallet, get a new address using the `wallet address` command
2. Send some BTC to the address using your Bitcoin node:
   ```bash
   bitcoin-cli -regtest sendtoaddress "your_wallet_address" 1.0
   ```
3. Wait for the transaction to be confirmed
4. List the UTXOs using `wallet utxos` command
5. Use the TXID and vout from the UTXO to create tokens

## Common Workflows

### Creating a Fungible Token

1. Create a wallet:
   ```bash
   python -m validator wallet create token_wallet
   ```

2. Get a deposit address:
   ```bash
   python -m validator wallet address token_wallet
   ```

3. Send BTC to the address and wait for confirmation

4. List UTXOs:
   ```bash
   python -m validator wallet utxos token_wallet
   ```

5. Create the token using a UTXO:
   ```bash
   python -m validator token create-fungible \
       --name "My Token" \
       --wallet-name token_wallet \
       --txid <from_utxos> \
       --vout <from_utxos> \
       --amount <from_utxos> \
       --total-supply 1000000
   ```

### Creating an NFT Collection

1. Prepare metadata JSON file (e.g., `metadata.json`):
   ```json
   {
       "attributes": [
           {"trait_type": "Color", "value": "Blue"},
           {"trait_type": "Size", "value": "Large"}
       ]
   }
   ```

2. Create the NFT:
   ```bash
   python -m validator token create-nft \
       --name "My NFT" \
       --wallet-name token_wallet \
       --txid <from_utxos> \
       --vout <from_utxos> \
       --amount <from_utxos> \
       --token-id "nft1" \
       --attributes-file metadata.json
   ``` 