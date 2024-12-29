# RGB Validator

A robust RGB validation software with multi-network Bitcoin support.

## Features

- **Multi-Network Support**:
  - Mainnet for production use
  - Testnet for integration testing
  - Regtest for local development
  
- **HD Wallet Management**:
  - BIP44 compliant wallet generation
  - Network-specific address derivation
  - Secure key storage and encryption
  
- **Token Operations**:
  - Create and manage fungible tokens
  - Network-aware token transfers
  - UTXO validation and tracking
  
- **Security**:
  - Encrypted wallet storage
  - Network isolation
  - Secure key management

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
BITCOIN_NETWORK=testnet

# Bitcoin RPC settings (ports: mainnet=8332, testnet=18332, regtest=18443)
BITCOIN_RPC_HOST=localhost
BITCOIN_RPC_PORT=18332
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password
```

### Basic Usage

1. Create a wallet:
```bash
# Create wallet for default network
python -m validator wallet create mywallet

# Or specify network
python -m validator wallet create mywallet --network testnet
```

2. Generate addresses:
```bash
python -m validator wallet address mywallet
```

3. List wallets:
```bash
python -m validator wallet list
```

## Network Support

### Mainnet
- Production network
- Real bitcoin transactions
- Addresses start with '1'
- Uses BIP44 coin type 0

### Testnet
- Test network
- Free test bitcoins
- Addresses start with 'm' or 'n'
- Uses BIP44 coin type 1

### Regtest
- Local testing network
- Instant block generation
- Same address format as testnet
- Perfect for development

## Development Setup

1. Start with Regtest:
```bash
# Configure for regtest
BITCOIN_NETWORK=regtest
BITCOIN_RPC_PORT=18443

# Create test wallet
python -m validator wallet create test --network regtest
```

2. Move to Testnet:
```bash
# Configure for testnet
BITCOIN_NETWORK=testnet
BITCOIN_RPC_PORT=18332

# Create testnet wallet
python -m validator wallet create test --network testnet
```

3. Production on Mainnet:
```bash
# Configure for mainnet
BITCOIN_NETWORK=mainnet
BITCOIN_RPC_PORT=8332

# Create mainnet wallet
python -m validator wallet create prod --network mainnet
```

## Security Considerations

1. Network Isolation
   - Keep separate wallets for each network
   - Never mix testnet and mainnet addresses
   - Use network-specific backups

2. Production Use
   - Always verify network settings
   - Double-check address formats
   - Use strong encryption passwords

3. Development
   - Start with regtest/testnet
   - Test all features before mainnet
   - Use proper error handling

## Documentation

- [Installation Guide](GUIDE.md#installation)
- [Configuration Guide](GUIDE.md#configuration)
- [Network Setup](GUIDE.md#network-support)
- [Wallet Management](GUIDE.md#working-with-wallets)
- [Token Operations](GUIDE.md#token-management)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test on regtest/testnet first
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
