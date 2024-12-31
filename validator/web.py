from flask import render_template, request, jsonify, flash, redirect, url_for, send_file
from decimal import Decimal
import json
import asyncio
import aiohttp
import hashlib
import time
import random
import os
import threading
from kademlia.network import Server
from collections import defaultdict
from .wallet import wallet_manager, WalletManager
from . import app, WALLETS_DIR  # Import app from __init__.py
import tempfile
from .database import BitcoinNodeConnector

# Lock for balance scanning
balance_scan_lock = threading.Lock()
active_scan = False

# Store active DHT nodes
active_nodes = {}

# Initialize the Bitcoin connector
bitcoin_connector = BitcoinNodeConnector()

def abort_active_scan():
    """Helper function to abort any active scan"""
    try:
        wallet_manager.abort_scan()
    except Exception as e:
        print(f"Error aborting scan: {str(e)}")

def get_wallet_with_balance(name: str) -> dict:
    """Helper function to get wallet data with balance"""
    global active_scan
    
    print(f"Getting wallet data for: {name}")
    wallet_data = wallet_manager.get_wallet(name, suppress_output=True)
    if not wallet_data:
        print(f"No wallet data found for: {name}")
        return None
    
    print(f"Initial wallet data: {wallet_data.keys()}")
        
    try:
        # Use lock to prevent concurrent balance scanning
        with balance_scan_lock:
            # If there's an active scan, abort it first
            if active_scan:
                abort_active_scan()
                time.sleep(1)  # Give some time for the abort to complete
            
            active_scan = True
            try:
                # Get balance
                balance = wallet_manager.get_balance(name, suppress_output=True)
                wallet_data['spendable_balance'] = balance.get('total_confirmed', 0) if balance else 0
                
                # Get all addresses with their balances
                address_balances = balance.get('addresses', {}) if balance else {}
                print(f"Address balances: {address_balances}")
                
                # Get detailed address information
                addresses = wallet_manager.get_addresses(name)
                print(f"Retrieved {len(addresses)} addresses for wallet {name}")
                print(f"Addresses: {[addr['address'] for addr in addresses]}")
                
                # Separate active and inactive addresses
                active_addresses = {}
                inactive_addresses = []
                
                for addr_info in addresses:
                    address = addr_info['address']
                    balance_info = address_balances.get(address, {})
                    confirmed_balance = balance_info.get('confirmed', 0) if isinstance(balance_info, dict) else 0
                    
                    if confirmed_balance > 0:
                        # Active address (has balance)
                        active_addresses[address] = confirmed_balance
                        print(f"Active address found: {address} with balance {confirmed_balance}")
                    else:
                        # Inactive address
                        inactive_addresses.append({
                            'address': address,
                            'derivation_path': addr_info['derivation_path'],
                            'public_key': addr_info['public_key'],
                            'private_key': addr_info['private_key']
                        })
                        print(f"Inactive address found: {address}")
                
                wallet_data['active_addresses'] = active_addresses
                wallet_data['inactive_addresses'] = inactive_addresses
                print(f"Total active addresses: {len(active_addresses)}")
                print(f"Total inactive addresses: {len(inactive_addresses)}")
                print(f"Final wallet data keys: {wallet_data.keys()}")
                
            finally:
                active_scan = False
                
    except Exception as balance_error:
        print(f"Warning: Could not get balance for wallet {name}: {str(balance_error)}")
        wallet_data['spendable_balance'] = 0
        wallet_data['active_addresses'] = {}
        wallet_data['inactive_addresses'] = []
    
    # Add frozen UTXO count
    wallet_data['frozen_utxo_count'] = len(wallet_manager.get_frozen_utxos(name))
    
    return wallet_data

def get_basic_wallet_info(name: str) -> dict:
    """Helper function to get basic wallet info without balance"""
    try:
        wallet_data = wallet_manager.get_wallet(name=name, suppress_output=True)
        if wallet_data:
            # Only return essential information
            return {
                'name': wallet_data['name'],
                'network': wallet_data.get('network', 'mainnet'),
                'address_type': wallet_data.get('address_type', 'segwit')
            }
    except Exception as e:
        print(f"Error loading basic wallet info for {name}: {str(e)}")
    return None

def get_all_wallets() -> list:
    """Helper function to get all wallets without balances"""
    wallets = []
    for wallet_file in WALLETS_DIR.glob("*.json"):
        try:
            wallet_data = get_basic_wallet_info(wallet_file.stem)
            if wallet_data:
                wallets.append(wallet_data)
        except Exception as e:
            print(f"Error loading wallet {wallet_file.stem}: {str(e)}")
            continue
    return wallets

def get_detailed_wallet_info(name: str) -> dict:
    """Get comprehensive wallet information including balances and stats"""
    wallet_data = wallet_manager.get_wallet(name=name, suppress_output=True)
    if not wallet_data:
        return None

    try:
        # Get UTXOs from database first
        utxos = wallet_manager.database.get_utxos(name, include_frozen=True)
        
        # Calculate balances from UTXOs
        frozen_utxos = [utxo for utxo in utxos if utxo.frozen]
        unfrozen_utxos = [utxo for utxo in utxos if not utxo.frozen]
        
        frozen_balance = sum(utxo.amount for utxo in frozen_utxos)
        spendable_balance = sum(utxo.amount for utxo in unfrozen_utxos)
        
        # Group unfrozen UTXOs by address to get active addresses
        active_addresses = {}
        for utxo in unfrozen_utxos:
            if utxo.address not in active_addresses:
                active_addresses[utxo.address] = Decimal('0')
            active_addresses[utxo.address] += utxo.amount
        
        # Enhance wallet data with additional information
        wallet_data.update({
            'spendable_balance': spendable_balance,
            'frozen_utxo_count': len(frozen_utxos),
            'frozen_utxos': frozen_utxos,
            'active_addresses': active_addresses
        })
        
        return wallet_data
    except Exception as e:
        print(f"Error getting detailed wallet info: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/rune20s')
def rune20s():
    return render_template('rune20s.html')

@app.route('/rune21s')
def rune21s():
    return render_template('rune21s.html')

@app.route('/wallets')
def wallets():
    try:
        wallets = get_all_wallets()
        if not wallets:
            print("No wallets found in directory:", WALLETS_DIR)
            
        return render_template('wallets.html', initial_wallets=wallets)
    except Exception as e:
        flash(f"Error loading wallets: {str(e)}", "error")
        return render_template('wallets.html', initial_wallets=[])

@app.route('/wallet/<name>')
def wallet_detail(name):
    try:
        print(f"\nLoading wallet detail for: {name}")
        wallet = get_wallet_with_balance(name)
        if not wallet:
            flash(f"Wallet '{name}' not found", "error")
            return redirect(url_for('wallets'))        
        
        # Enable debug mode for the template
        wallet['debug_mode'] = True
        
        return render_template(
            'wallet.html',
            wallet=wallet,
            request=request
        )
    except Exception as e:
        print(f"Error in wallet_detail: {str(e)}")
        flash(f"Error loading wallet: {str(e)}", "error")
        return redirect(url_for('wallets'))

@app.route('/api/wallets')
def list_wallets():
    try:
        wallets = get_all_wallets()
        if not wallets:
            print("No wallets found in directory:", WALLETS_DIR)
            
        return jsonify({'wallets': wallets})
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/api/wallets/create', methods=['POST'])
def create_wallet():
    try:
        # Validate inputs
        name = request.form.get('name')
        if not name:
            return jsonify({'error': 'Wallet name is required'}), 400
            
        network = request.form.get('network', 'mainnet')
        if network not in ['mainnet', 'testnet', 'regtest']:
            return jsonify({'error': 'Invalid network type'}), 400
            
        address_type = request.form.get('address_type', 'taproot')
        if address_type not in ['legacy', 'taproot']:
            return jsonify({'error': 'Invalid address type. Only legacy and taproot are supported'}), 400
            
        # Check if wallet already exists
        wallet_path = WALLETS_DIR / f"{name}.json"
        if wallet_path.exists():
            flash(f"Wallet '{name}' already exists", "error")
            return redirect(url_for('wallets'))
            
        # Create wallet with fixed address count of 1
        wallet = wallet_manager.create_wallet(
            name=name,
            network=network,
            address_type=address_type,
            address_count=1  # Fixed to 1 address
        )
        
        flash("Wallet created successfully!", "success")
        # Redirect to the wallet detail page
        return redirect(url_for('wallet_detail', name=name))
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/api/wallets/<name>/info')
def get_wallet_info(name):
    try:
        wallet_data = get_wallet_with_balance(name)
        if not wallet_data:
            return jsonify({'error': f"Wallet '{name}' not found"}), 404
            
        return jsonify({'wallet': wallet_data})
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/api/wallets/<name>/generate', methods=['POST'])
def generate_address(name):
    try:
        address = wallet_manager.generate_address(name)
        flash(f"New address generated successfully: {address}", "success")
        return redirect(url_for('wallet_detail', name=name, tab='inactive'))
    except Exception as e:
        flash(f"Error generating address: {str(e)}", "error")
        return redirect(url_for('wallet_detail', name=name, tab='inactive'))

@app.route('/api/wallets/<name>/balance')
def get_balance(name):
    try:
        balance = wallet_manager.get_balance(name, suppress_output=True)
        return jsonify(balance)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/api/wallets/<name>/send', methods=['POST'])
def send_bitcoin(name):
    try:
        address = request.form.get('address')
        amount = Decimal(request.form.get('amount'))
        memo = request.form.get('memo')
        fee_rate = float(request.form.get('fee_rate', 5.0))
        
        txid = wallet_manager.send_bitcoin(
            name=name,
            to_address=address,
            amount=amount,
            memo=memo,
            fee_rate=fee_rate
        )
        
        return jsonify({
            'status': 'success',
            'txid': txid
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/api/wallets/<name>/freeze-utxo', methods=['POST'])
def freeze_utxo(name):
    try:
        txid = request.form.get('txid')
        vout = int(request.form.get('vout'))
        if not txid or vout is None:
            flash("Missing UTXO information", "error")
            return redirect(url_for('wallet_detail', name=name, tab='utxos'))
            
        # Create and freeze the UTXO
        wallet_manager.create_and_freeze_utxo(
            name=name,
            amount=Decimal(str(request.form.get('amount'))),
            memo="Frozen via web interface"
        )
        flash("UTXO frozen successfully", "success")
        return redirect(url_for('wallet_detail', name=name, tab='utxos'))
    except Exception as e:
        flash(f"Error freezing UTXO: {str(e)}", "error")
        return redirect(url_for('wallet_detail', name=name, tab='utxos'))

@app.route('/api/wallets/<name>/consolidate', methods=['POST'])
def consolidate_utxos(name):
    try:
        fee_rate = float(request.form.get('fee_rate', 5.0))
        batch_size = int(request.form.get('batch_size', 50))
        
        txid = wallet_manager.consolidate_utxos(
            name=name,
            fee_rate=fee_rate,
            batch_size=batch_size
        )
        
        return jsonify({
            'status': 'success',
            'txid': txid
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/api/wallets/<name>/network-info')
def get_network_info(name):
    try:
        network_type = request.args.get('network_type')
        address_type = request.args.get('address_type')
        
        wallet_manager.get_network_info(name, network_type, address_type)
        return jsonify({
            'status': 'success'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/network')
def network():
    try:
        wallets = []
        for wallet_file in WALLETS_DIR.glob("*.json"):
            try:
                wallet_data = wallet_manager.get_wallet(wallet_file.stem, suppress_output=True)
                if wallet_data:
                    wallets.append(wallet_data)
            except Exception as e:
                print(f"Error loading wallet {wallet_file.stem}: {str(e)}")
                continue
        return render_template('network.html', wallets=wallets)
    except Exception as e:
        flash(f"Error loading wallets: {str(e)}", "error")
        return render_template('network.html', wallets=[])

@app.route('/network/nodes')
def get_nodes():
    nodes = []
    for node_id, node_info in active_nodes.items():
        nodes.append({
            'node_id': node_id,
            'role': 'Bootstrap' if node_info.get('is_bootstrap') else 'Peer',
            'network': node_info.get('network', 'unknown'),
            'status': node_info.get('status', 'unknown'),
            'peers': node_info.get('peers', [])
        })
    return jsonify({'nodes': nodes})

@app.route('/network/sync/dht', methods=['POST'])
def start_dht_sync():
    try:
        wallet_name = request.form.get('wallet_name')
        port = int(request.form.get('port', 8000))
        is_bootstrap = request.form.get('is_bootstrap') == 'true'
        bootstrap_node = request.form.get('bootstrap_node')

        # Generate a unique node ID
        node_id = hashlib.sha256(f"{wallet_name}:{port}:{time.time()}".encode()).hexdigest()

        # Create event loop if it doesn't exist
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Initialize DHT node
        node = Server()
        node.node_id = node_id
        
        async def start_node():
            await node.listen(port)
            
            if not is_bootstrap and bootstrap_node:
                host, bootstrap_port = bootstrap_node.split(':')
                bootstrap_port = int(bootstrap_port)
                
                # Try to bootstrap with retries
                max_retries = 3
                retry_delay = 2
                
                for attempt in range(max_retries):
                    try:
                        await node.bootstrap([(host, bootstrap_port)])
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise Exception(f"Failed to connect to bootstrap node after {max_retries} attempts")
                        await asyncio.sleep(retry_delay)

            # Store node information
            active_nodes[node_id] = {
                'node': node,
                'is_bootstrap': is_bootstrap,
                'wallet_name': wallet_name,
                'network': 'mainnet',  # You might want to make this configurable
                'status': 'active',
                'peers': []
            }

            # Start periodic tasks
            asyncio.create_task(update_node_status(node_id))
            asyncio.create_task(broadcast_wallet_state(node_id))

        loop.run_until_complete(start_node())

        return jsonify({
            'status': 'success',
            'node_id': node_id,
            'message': f"{'Bootstrap' if is_bootstrap else 'Peer'} node started successfully"
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

@app.route('/network/sync/dht/stop/<node_id>', methods=['POST'])
def stop_dht_sync(node_id):
    try:
        if node_id not in active_nodes:
            return jsonify({
                'status': 'error',
                'error': 'Node not found'
            }), 404

        node_info = active_nodes[node_id]
        node = node_info['node']

        # Create event loop if it doesn't exist
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def stop_node():
            await node.stop()
            del active_nodes[node_id]

        loop.run_until_complete(stop_node())

        return jsonify({
            'status': 'success',
            'message': 'Node stopped successfully'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400

async def update_node_status(node_id):
    """Periodically update node status and peer list."""
    while node_id in active_nodes:
        try:
            node_info = active_nodes[node_id]
            node = node_info['node']

            # Update peer list
            peers = []
            for bucket in node.protocol.router.buckets:
                peers.extend(bucket.get_nodes())
            
            node_info['peers'] = [
                {
                    'id': peer.id.hex(),
                    'ip': peer.ip,
                    'port': peer.port
                }
                for peer in peers
            ]

            await asyncio.sleep(10)  # Update every 10 seconds
        except Exception as e:
            print(f"Error updating node status: {e}")
            await asyncio.sleep(10)

async def broadcast_wallet_state(node_id):
    """Periodically broadcast wallet state to the network."""
    while node_id in active_nodes:
        try:
            node_info = active_nodes[node_id]
            node = node_info['node']

            # Get wallet info
            wallet = wallet_manager.get_wallet(node_info['wallet_name'], suppress_output=True)
            balance = wallet_manager.get_balance(node_info['wallet_name'], suppress_output=True)

            # Prepare minimal wallet state
            state = {
                'node_id': node_id,
                'wallet_name': node_info['wallet_name'],
                'network': wallet.get('network', 'mainnet') if wallet else 'mainnet',
                'balance': balance.get('total_confirmed', 0) if balance else 0,
                'is_bootstrap': node_info['is_bootstrap'],
                'timestamp': int(time.time()),
                'status': 'active'
            }

            # Broadcast state to network
            await node.set(f'wallet_state:{node_id}', json.dumps(state))
            await asyncio.sleep(30)  # Broadcast every 30 seconds
        except Exception as e:
            print(f"Error broadcasting wallet state: {e}")
            await asyncio.sleep(30) 

@app.route('/api/wallets/<name>/delete', methods=['POST'])
def delete_wallet(name):
    try:
        # Check if wallet exists
        wallet_data = get_basic_wallet_info(name)
        if not wallet_data:
            return jsonify({
                'status': 'error',
                'error': f"Wallet '{name}' not found"
            }), 404

        # Delete the wallet
        wallet_manager.delete_wallet(name)
        
        flash(f"Wallet '{name}' has been permanently deleted.", "success")
        return jsonify({
            'status': 'success',
            'message': f"Wallet '{name}' deleted successfully"
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 400 

@app.route('/api/wallets/<name>/export')
def export_wallet(name):
    try:
        wallet_data = wallet_manager.get_wallet(name)
        if not wallet_data:
            flash(f"Wallet '{name}' not found", "error")
            return redirect(url_for('wallets'))
            
        # Create a temporary file for the wallet backup
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            json.dump(wallet_data, tmp, indent=2)
            tmp_path = tmp.name
            
        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f"{name}_backup.json",
            mimetype='application/json'
        )
    except Exception as e:
        flash(f"Error exporting wallet: {str(e)}", "error")
        return redirect(url_for('wallet_detail', name=name, tab='export')) 

@app.route('/api/connect', methods=['POST'])
def connect_node():
    success = bitcoin_connector.connect_to_electrum()
    return jsonify({"success": success})

@app.route('/api/transaction/<txid>')
def get_transaction(txid):
    try:
        tx_details = bitcoin_connector.get_transaction_details(txid)
        return jsonify(tx_details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500 

@app.route('/explorer')
def explorer():
    """Bitcoin explorer page"""
    try:
        # Test connection by getting network info
        bitcoin_connector.get_network_info()
        return render_template('explorer.html')
    except Exception as e:
        flash(f"Error connecting to Bitcoin network: {str(e)}", "error")
        return render_template('explorer.html')

@app.route('/api/explorer/network-info')
def get_bitcoin_network_info():
    """Get Bitcoin network information"""
    try:
        network_info = bitcoin_connector.get_network_info()
        return jsonify(network_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/explorer/mempool')
def get_mempool_info():
    """Get mempool information"""
    try:
        mempool_info = bitcoin_connector.get_mempool_info()
        return jsonify(mempool_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/explorer/latest-blocks')
def get_latest_blocks():
    """Get latest blocks"""
    try:
        blocks = bitcoin_connector.get_latest_blocks()
        return jsonify(blocks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/explorer/block/<block_hash>')
def get_block_info(block_hash):
    """Get block information"""
    try:
        block_info = bitcoin_connector.get_block_details(block_hash)
        return jsonify(block_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/explorer/tx/<txid>')
def get_transaction_info(txid):
    """Get transaction information"""
    try:
        tx_info = bitcoin_connector.get_transaction_details(txid)
        return jsonify(tx_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/explorer/search', methods=['POST'])
def search_blockchain():
    """Search for blocks, transactions, or addresses"""
    try:
        query = request.json.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Empty search query'}), 400

        # Try to get transaction details
        try:
            tx_info = bitcoin_connector.get_transaction_details(query)
            return jsonify({'type': 'transaction', 'data': tx_info})
        except:
            pass

        # Try to get block details (by hash or height)
        try:
            # Try as block hash first
            block_info = bitcoin_connector.get_block_details(query)
            return jsonify({'type': 'block', 'data': block_info})
        except:
            # Try as block height
            try:
                if query.isdigit():
                    block_info = bitcoin_connector.get_block_by_height(int(query))
                    return jsonify({'type': 'block', 'data': block_info})
            except:
                pass

        return jsonify({'error': 'No results found'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500 

@app.route('/block')
def block_detail():
    """Block details page"""
    try:
        return render_template('block.html')
    except Exception as e:
        flash(f"Error loading block details: {str(e)}", "error")
        return render_template('block.html')

@app.route('/transaction')
def transaction_detail():
    """Transaction details page"""
    try:
        return render_template('transaction.html')
    except Exception as e:
        flash(f"Error loading transaction details: {str(e)}", "error")
        return render_template('transaction.html')

@app.route('/api/explorer/block/<identifier>/txs/<int:start_index>')
def get_block_transactions(identifier, start_index):
    """Get transactions in a block with pagination"""
    try:
        # If identifier is a height, get the block hash first
        if identifier.isdigit():
            block = bitcoin_connector.get_block_by_height(int(identifier))
            block_hash = block['hash']
        else:
            block_hash = identifier

        transactions = bitcoin_connector.get_block_txs(block_hash, start_index)
        return jsonify(transactions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500 