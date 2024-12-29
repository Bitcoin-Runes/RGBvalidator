# RGB Validator

A robust RGB validation software with advanced Bitcoin smart contract support and multi-network capabilities.

## Features

### Multi-Network Support
- **Mainnet**: Production network (real BTC)
- **Testnet**: Testing network (test BTC)
- **Regtest**: Local development with Polar

### Advanced Wallet Management
- **Multiple Address Types**:
  - Taproot (P2TR): Enhanced privacy and smart contracts
  - Native SegWit (P2WPKH): Efficient transactions
  - Nested SegWit (P2SH-P2WPKH): Backward compatibility
  - Legacy (P2PKH): Maximum compatibility

- **HD Wallet Features**:
  - BIP44/49/84/86 compliant
  - Network-specific derivation paths
  - Secure key storage and encryption
  - Multiple address generation

### Smart Contract Support
- **Taproot Capabilities**:
  - MAST (Merkelized Alternative Script Trees)
  - Schnorr signatures
  - Complex script conditions
  - Enhanced privacy features

- **Contract Types**:
  - Time-locked contracts
  - Multi-signature wallets
  - Atomic swaps
  - Hash Time Locked Contracts (HTLCs)

### Token Operations
- Create and manage fungible tokens
- Network-aware token transfers
- UTXO validation and tracking
- Atomic swap support

### Security Features
- Encrypted wallet storage
- Network isolation
- Secure key management
- Address validation

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/anoncodemonkey/RGBvalidator.git
cd token-validator

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Create a `.env` file:
```env
# Choose network: mainnet, testnet, or regtest
BITCOIN_NETWORK=regtest  # Default for development

# Bitcoin RPC settings
BITCOIN_RPC_HOST=localhost
BITCOIN_RPC_PORT=18443  # Regtest default
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password
```

### Wallet Management

1. Create wallets for different networks:
```bash
# Create Taproot wallet (recommended for new projects)
python -m validator wallet create taproot_wallet --type taproot --network regtest

# Create SegWit wallet
python -m validator wallet create segwit_wallet --type segwit --network testnet

# Create Legacy wallet
python -m validator wallet create legacy_wallet --type legacy --network mainnet
```

2. Generate addresses:
```bash
# Generate single address
python -m validator wallet generate wallet_name

# Generate multiple addresses
python -m validator wallet generate-batch wallet_name --count 5
```

3. View wallet information:
```bash
# List all wallets
python -m validator wallet list

# View specific wallet details
python -m validator wallet info wallet_name

# View network-specific addresses
python -m validator wallet addresses wallet_name
```

## Network-Specific Features

### Regtest (Local Development)
- Use with Polar for testing
- Instant block generation
- Address formats:
  * Taproot: bcrt1p...
  * SegWit: bcrt1q...
  * Nested SegWit: 2...
  * Legacy: m/n...

### Testnet (Testing)
- Free test bitcoins
- Address formats:
  * Taproot: tb1p...
  * SegWit: tb1q...
  * Nested SegWit: 2...
  * Legacy: m/n...
- Faucet: https://testnet-faucet.mempool.co/

### Mainnet (Production)
- Real bitcoin transactions
- Address formats:
  * Taproot: bc1p...
  * SegWit: bc1q...
  * Nested SegWit: 3...
  * Legacy: 1...

## Smart Contract Development

### Taproot Contracts
```python
# Example Timelock Contract
{
  "contract_type": "timelock",
  "unlock_time": "2024-12-31T23:59:59Z",
  "conditions": {
    "before_timeout": ["pubkey_A"],
    "after_timeout": ["pubkey_B"]
  }
}
```

### Atomic Swaps
```python
# Example Token Swap
{
  "contract_type": "atomic_swap",
  "asset_offered": {"type": "bitcoin", "amount": 1.0},
  "asset_requested": {"type": "token", "amount": 1000},
  "timeout": 24  # hours
}
```

## Security Best Practices

1. Network Isolation
   - Use separate wallets for each network
   - Verify address formats before sending
   - Use network-specific backups

2. Development Workflow
   - Start with regtest/Polar
   - Move to testnet for integration
   - Thorough testing before mainnet

3. Production Safeguards
   - Double-check network settings
   - Verify address formats
   - Use strong encryption
   - Keep secure backups

## Documentation

- [User Guide](GUIDE.md)
- [Smart Contract Guide](CONTRACTS.md)
- [Network Setup](NETWORKS.md)
- [Token Management](TOKENS.md)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test thoroughly on regtest/testnet
4. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file
