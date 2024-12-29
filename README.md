# Token Validator

A Python-based token validation system that uses Bitcoin UTXOs for token creation and verification. This system allows you to create and manage both fungible and non-fungible tokens (NFTs) backed by Bitcoin UTXOs.

## Features

- **Bitcoin Integration**: Direct integration with Bitcoin node for UTXO verification
- **Wallet Management**: Create and manage Bitcoin wallets
- **Token Types**:
  - Fungible Tokens (FT)
  - Non-Fungible Tokens (NFT)
- **Multiple Interfaces**:
  - CLI interface with rich formatting
  - RESTful API with FastAPI
- **UTXO Verification**: Ensures tokens are backed by valid Bitcoin UTXOs
- **Local Database**: SQLite storage for token and wallet data
- **Metadata Support**: Rich metadata support for NFTs

## Requirements

- Python 3.8 or higher
- Bitcoin Core node (local or remote)
- SQLite 3

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/validator.git
   cd validator
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure Bitcoin node connection:
   ```bash
   cp .env.example .env
   # Edit .env with your Bitcoin node credentials
   ```

4. Start the API server:
   ```bash
   python -m validator serve
   ```

5. Or use the CLI:
   ```bash
   python -m validator wallet create my_wallet
   ```

## Documentation

- [User Guide](GUIDE.md) - Detailed instructions for using the validator
- [API Documentation](http://localhost:8000/docs) - Interactive API documentation (available when server is running)

## Project Structure

```
validator/
├── __init__.py
├── __main__.py
├── api.py          # FastAPI implementation
├── cli.py          # CLI implementation
├── models.py       # Data models
├── database.py     # Database operations
├── bitcoin_client.py # Bitcoin node interface
└── config.py       # Configuration management
```

## Development Status

See [Project Status](ai/project-update.md) for current development status and roadmap.

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Bitcoin Core for the reference implementation
- FastAPI for the modern web framework
- Typer for the CLI interface
- Rich for beautiful terminal formatting
