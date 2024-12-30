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

- **Transaction Management**:
  - Send bitcoin with custom fee rates
  - Add memos to transactions
  - UTXO tracking and management
  - Freeze specific UTXOs
  - Custom fee rate support (sat/vB)

### UTXO Management
- **Freezing Capabilities**:
  - Create and freeze specific UTXOs
  - Add memos to frozen UTXOs
  - Track frozen UTXOs separately
  - Prevent spending of frozen UTXOs

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

### P2P Network Features
- **Distributed Hash Table (DHT)**:
  - Peer discovery
  - Decentralized network topology
  - Automatic peer routing
- **Gossip Protocol**:
  - Wallet state synchronization
  - Real-time updates
  - Efficient message propagation
  - Topic-based pub/sub

## Quick Start

### Docker Installation (Recommended)

The easiest way to get started is using Docker:

```bash
# Clone the repository
git clone https://github.com/anoncodemonkey/RGBvalidator.git
cd token-validator

# Create .env file
cat > .env << EOL
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password
SECRET_KEY=your-secret-key-here
EOL

# Start the services
docker-compose up -d

# Check services status
docker-compose ps

# View logs
docker-compose logs -f
```

The Docker setup provides:
- Automatic Bitcoin Core setup (regtest mode)
- Pre-configured validator service
- Persistent data storage
- Health monitoring
- Automatic restarts

### Manual Installation (Alternative)

If you prefer not to use Docker:

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

#### Using Docker (Recommended)
Edit the `.env` file:
```env
# Bitcoin RPC settings (used by both services)
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password
SECRET_KEY=your-secret-key-here
```

#### Manual Configuration
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

### Using the Validator

With Docker:
```bash
# Execute commands inside the validator container
docker-compose exec validator python -m validator wallet create my_wallet
docker-compose exec validator python -m validator wallet generate my_wallet
```

Without Docker:
```bash
python -m validator wallet create my_wallet
python -m validator wallet generate my_wallet
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
python -m validator wallet generate wallet_name --count 5
```

3. Send Bitcoin:
```bash
# Send with default fee rate (5 sat/vB for regtest)
python -m validator wallet send wallet_name recipient_address 0.1

# Send with custom fee rate and memo
python -m validator wallet send wallet_name recipient_address 0.1 --fee-rate 10 --memo "Payment for services"
```

4. Manage UTXOs:
```bash
# Create and freeze a UTXO
python -m validator wallet freeze-utxo wallet_name 0.1 --memo "Reserved for special purpose"

# Check wallet balance (includes frozen UTXOs)
python -m validator wallet balance wallet_name
```

5. View wallet information:
```bash
# List all wallets
python -m validator wallet list

# View specific wallet details
python -m validator wallet info wallet_name

# View network-specific addresses
python -m validator wallet network wallet_name
```

## Network-Specific Features

### Regtest (Local Development)
- Use with Polar for testing
- Instant block generation
- Default fee rate: 5 sat/vB
- Address formats:
  * Taproot: bcrt1p...
  * SegWit: bcrt1q...
  * Nested SegWit: 2...
  * Legacy: m/n...

### Testnet (Testing)
- Free test bitcoins
- Dynamic fee estimation
- Address formats:
  * Taproot: tb1p...
  * SegWit: tb1q...
  * Nested SegWit: 2...
  * Legacy: m/n...
- Faucet: https://testnet-faucet.mempool.co/

### Mainnet (Production)
- Real bitcoin transactions
- Dynamic fee estimation
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

## Development Environment

### Using Docker (Recommended)

1. Start development environment:
```bash
docker-compose up -d
```

2. Access logs:
```bash
docker-compose logs -f validator  # Validator logs
docker-compose logs -f bitcoin   # Bitcoin Core logs
```

3. Execute commands:
```bash
# Create wallet
docker-compose exec validator python -m validator wallet create dev_wallet

# Generate address
docker-compose exec validator python -m validator wallet generate dev_wallet

# Check balance
docker-compose exec validator python -m validator wallet balance dev_wallet
```

4. Stop environment:
```bash
docker-compose down  # Stop services
docker-compose down -v  # Stop services and remove volumes
```

### Data Persistence

Docker volumes are used to persist data:
- `validator_data`: Wallet and application data
- `validator_logs`: Application logs
- `bitcoin_data`: Bitcoin Core data

### Troubleshooting Docker Setup

1. Check service status:
```bash
docker-compose ps
```

2. View service logs:
```bash
docker-compose logs -f
```

3. Restart services:
```bash
docker-compose restart
```

4. Reset environment:
```bash
docker-compose down -v
docker-compose up -d
```

## Experimental Features

### DHT and Gossip Protocol Testing

The `cubaan` command allows you to experiment with DHT and gossip protocol functionality:

1. Start the first instance:
```bash
# With Docker:
docker-compose exec validator python -m validator cubaan my_wallet --port 8000

# Without Docker:
python -m validator cubaan my_wallet --port 8000
```

2. Start the second instance (in a different terminal):
```bash
# Get the multiaddr from the first instance output and use it here
# With Docker:
docker-compose exec validator python -m validator cubaan other_wallet --port 8001 --peer /ip4/127.0.0.1/tcp/8000/p2p/QmHash...

# Without Docker:
python -m validator cubaan other_wallet --port 8001 --peer /ip4/127.0.0.1/tcp/8000/p2p/QmHash...
```

The instances will:
- Automatically discover each other using DHT
- Share wallet states using gossip protocol
- Broadcast updates every 10 seconds
- Display received messages from other peers

To test different networks:
```bash
# Use custom topic for specific network testing
python -m validator cubaan my_wallet --port 8000 --topic testnet-sync

# Connect to specific peer with custom topic
python -m validator cubaan other_wallet --port 8001 --peer /ip4/127.0.0.1/tcp/8000/p2p/QmHash... --topic testnet-sync
```
