# Token Validator User Guide

## Table of Contents

1. [Installation](#installation)
   - [Docker Installation](#docker-installation)
   - [Manual Installation](#manual-installation)
2. [Configuration](#configuration)
3. [Network Support](#network-support)
4. [Working with Wallets](#working-with-wallets)
5. [Transaction Management](#transaction-management)
6. [UTXO Management](#utxo-management)
7. [Token Management](#token-management)
8. [Backup and Recovery](#backup-and-recovery)
9. [Troubleshooting](#troubleshooting)

## Installation

### Docker Installation (Recommended)

The simplest way to get started is using Docker:

1. Clone the repository:
```bash
git clone https://github.com/yourusername/token-validator.git
cd token-validator
```

2. Create environment file:
```bash
cat > .env << EOL
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password
SECRET_KEY=your-secret-key-here
EOL
```

3. Start services:
```bash
docker-compose up -d
```

4. Verify installation:
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs -f
```

#### Docker Benefits
- Pre-configured Bitcoin Core node
- Automatic service orchestration
- Built-in health monitoring
- Data persistence
- Automatic restarts
- Isolated environment

### Manual Installation

#### Prerequisites

- Python 3.11 or higher
- Bitcoin Core node (optional for mainnet/testnet)
- SQLite3 (included in Python)

### Setup Steps

1. Clone the repository:
```bash
git clone https://github.com/yourusername/token-validator.git
cd token-validator
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### Docker Configuration

1. Environment Setup:
Edit `.env` file with your settings:
```env
# Bitcoin RPC Configuration
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password
SECRET_KEY=your-secret-key-here

# Optional overrides
BITCOIN_RPC_HOST=bitcoin
BITCOIN_RPC_PORT=18443
```

2. Service Configuration:
The `docker-compose.yml` file provides:
- Validator service configuration
- Bitcoin Core setup
- Network settings
- Volume management
- Health checks

3. Accessing Services:
```bash
# Execute validator commands
docker-compose exec validator python -m validator [command]

# Access Bitcoin Core
docker-compose exec bitcoin bitcoin-cli -regtest [command]
```

### Manual Configuration

### Environment Setup

Create a `.env` file with your network settings:

```env
# Network Selection (mainnet, testnet, regtest)
BITCOIN_NETWORK=testnet

# Bitcoin RPC Configuration
BITCOIN_RPC_HOST=localhost
BITCOIN_RPC_PORT=18332  # Port varies by network
BITCOIN_RPC_USER=your_username
BITCOIN_RPC_PASSWORD=your_password

# Application Settings
APP_SECRET_KEY=your_secret_key
DATABASE_URL=sqlite:///validator.db
```

### Network-Specific Ports

- Mainnet: 8332
- Testnet: 18332
- Regtest: 18443

## Network Support

### Working with Docker Networks

#### Mainnet
```bash
# Update docker-compose.yml bitcoin service
services:
  bitcoin:
    command:
      -server=1
      -rpcallowip=0.0.0.0/0
      # ... other settings ...

# Start services
docker-compose up -d

# Execute commands
docker-compose exec validator python -m validator wallet create mainnet_wallet --network mainnet
```

#### Testnet
```bash
# Update docker-compose.yml bitcoin service
services:
  bitcoin:
    command:
      -testnet=1
      -server=1
      # ... other settings ...

# Start services
docker-compose up -d

# Execute commands
docker-compose exec validator python -m validator wallet create testnet_wallet --network testnet
```

#### Regtest (Default)
```bash
# Default configuration works with regtest
docker-compose up -d

# Execute commands
docker-compose exec validator python -m validator wallet create regtest_wallet --network regtest
```

### Manual Network Setup

### Working with Mainnet

```bash
# Configure for mainnet
export BITCOIN_NETWORK=mainnet
export BITCOIN_RPC_PORT=8332

# Create mainnet wallet
python -m validator wallet create mainnet_wallet --network mainnet

# Generate mainnet address
python -m validator wallet address mainnet_wallet
```

### Working with Testnet

```bash
# Configure for testnet
export BITCOIN_NETWORK=testnet
export BITCOIN_RPC_PORT=18332

# Create testnet wallet
python -m validator wallet create testnet_wallet --network testnet

# Generate testnet address
python -m validator wallet address testnet_wallet
```

### Working with Regtest

```bash
# Configure for regtest
export BITCOIN_NETWORK=regtest
export BITCOIN_RPC_PORT=18443

# Create regtest wallet
python -m validator wallet create regtest_wallet --network regtest

# Generate regtest address
python -m validator wallet address regtest_wallet
```

## Working with Wallets

### Docker Wallet Commands

1. Create Wallet:
```bash
docker-compose exec validator python -m validator wallet create <name> [--network <network>] [--type <address_type>]
```

2. List Wallets:
```bash
docker-compose exec validator python -m validator wallet list
```

3. Generate Address:
```bash
docker-compose exec validator python -m validator wallet generate <name> [--count <number>]
```

4. Get Balance:
```bash
docker-compose exec validator python -m validator wallet balance <name>
```

5. View Network Info:
```bash
docker-compose exec validator python -m validator wallet network <name>
```

6. Export Wallet:
```bash
docker-compose exec validator python -m validator wallet export <name> <path>
```

7. Import Wallet:
```bash
docker-compose exec validator python -m validator wallet import <path>
```

### Manual Wallet Commands

1. Create Wallet:
```bash
python -m validator wallet create <name> [--network <network>] [--type <address_type>]
```

2. List Wallets:
```bash
python -m validator wallet list
```

3. Generate Address:
```bash
python -m validator wallet generate <name> [--count <number>]
```

4. Get Balance:
```bash
python -m validator wallet balance <name>
```

5. View Network Info:
```bash
python -m validator wallet network <name>
```

6. Export Wallet:
```bash
python -m validator wallet export <name> <path>
```

7. Import Wallet:
```bash
python -m validator wallet import <path>
```

### Network-Specific Features

- Each wallet is network-aware
- Addresses are automatically formatted for the correct network
- Separate storage for each network's wallets
- Network-specific backup files

## Transaction Management

### Sending Bitcoin

1. Basic Send:
```bash
python -m validator wallet send <wallet_name> <recipient_address> <amount>
```

2. Send with Custom Fee Rate:
```bash
python -m validator wallet send <wallet_name> <recipient_address> <amount> --fee-rate <sat/vB>
```

3. Send with Memo:
```bash
python -m validator wallet send <wallet_name> <recipient_address> <amount> --memo "Payment description"
```

### Fee Rate Guidelines

- **Regtest**: Default 5 sat/vB
- **Testnet/Mainnet**: Dynamic fee estimation
- Custom fee rates: 1-100 sat/vB recommended

### Transaction Features

- Automatic UTXO selection
- Change address generation
- Memo support
- Custom fee rates
- Transaction tracking

## UTXO Management

### Freezing UTXOs

1. Create and Freeze UTXO:
```bash
python -m validator wallet freeze-utxo <wallet_name> <amount> [--memo "Purpose of freeze"]
```

2. View Frozen UTXOs:
```bash
python -m validator wallet balance <wallet_name>
# Shows both available and frozen UTXOs
```

### UTXO Features

- Create specific value UTXOs
- Freeze UTXOs to prevent spending
- Add memos for tracking
- Automatic UTXO tracking
- Balance segregation (available vs frozen)

### Best Practices

1. UTXO Creation:
   - Use meaningful memos
   - Consider fee implications
   - Plan UTXO values carefully

2. UTXO Management:
   - Regular balance checks
   - Document frozen UTXOs
   - Monitor UTXO states

## Token Management

### Token Commands

1. Create Token:
```bash
python -m validator token create <name> <supply> [--decimals <decimals>] [--network <network>]
```

2. List Tokens:
```bash
python -m validator token list [--network <network>]
```

3. Transfer Token:
```bash
python -m validator token transfer <token_id> <recipient> <amount>
```

4. Get Token Info:
```bash
python -m validator token info <token_id>
```

### Network Considerations

- Tokens are bound to their creation network
- Cross-network transfers are not supported
- Each network maintains its own token registry

## Backup and Recovery

### Backup Commands

1. Create Backup:
```bash
python -m validator backup create [--network <network>]
```

2. List Backups:
```bash
python -m validator backup list
```

3. Restore from Backup:
```bash
python -m validator backup restore <backup_id>
```

### Network-Specific Backups

- Separate backup files for each network
- Network information included in backup metadata
- Restore validates network compatibility

## Troubleshooting

### Docker-Specific Issues

1. Service Status:
```bash
# Check service status
docker-compose ps

# View detailed status
docker-compose ps validator
docker-compose ps bitcoin
```

2. Logs:
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f validator
docker-compose logs -f bitcoin
```

3. Service Management:
```bash
# Restart services
docker-compose restart

# Rebuild services
docker-compose up -d --build

# Reset environment
docker-compose down -v
docker-compose up -d
```

4. Common Docker Issues:
- Port conflicts: Check if ports 5000 or 18443 are in use
- Volume permissions: Ensure proper ownership of mounted volumes
- Network connectivity: Verify services can communicate
- Resource constraints: Monitor container resource usage

### General Issues

1. Network Connection:
```bash
# Test network connection
python -m validator network test
```

2. Address Validation:
```bash
# Validate address format
python -m validator wallet validate <address>
```

3. Network Status:
```bash
# Check network status
python -m validator network status
```

### Network-Specific Problems

1. Mainnet Issues:
- Check Bitcoin Core sync status
- Verify RPC credentials
- Confirm network port (8332)

2. Testnet Issues:
- Ensure testnet node is running
- Check testnet port (18332)
- Verify testnet faucet access

3. Regtest Issues:
- Confirm regtest mode is active
- Check regtest port (18443)
- Verify block generation 