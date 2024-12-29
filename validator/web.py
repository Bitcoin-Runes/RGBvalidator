from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, flash, session
)
from functools import wraps
import os

from .database import Database
from .models import TokenType, FungibleToken, NonFungibleToken, UTXOReference
from .bitcoin_client import bitcoin_client
from .backup import backup_manager
from .batch import batch_processor
from .auth import authenticate_user, create_access_token
from .logging_config import logger

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")  # Change in production
db = Database()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = authenticate_user(username, password)
        if user:
            session['user'] = username
            return redirect(url_for('index'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# Wallet Routes
@app.route('/wallets')
@login_required
def wallets():
    wallet_list = db.list_wallets()
    return render_template('wallets.html', wallets=wallet_list)

@app.route('/wallets/create', methods=['POST'])
@login_required
def create_wallet():
    try:
        wallet_name = request.form.get('wallet_name')
        wallet_info = bitcoin_client.create_wallet(wallet_name)
        return jsonify(wallet_info)
    except Exception as e:
        logger.error(f"Error creating wallet: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/wallets/<wallet_name>/utxos')
@login_required
def wallet_utxos(wallet_name):
    try:
        utxos = bitcoin_client.get_utxos(wallet_name)
        return jsonify(utxos)
    except Exception as e:
        logger.error(f"Error getting UTXOs: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Token Routes
@app.route('/tokens')
@login_required
def tokens():
    return render_template('tokens.html')

@app.route('/tokens/create', methods=['GET', 'POST'])
@login_required
def create_token():
    if request.method == 'POST':
        try:
            data = request.form.to_dict()
            token_type = data.get('token_type')
            
            # Create UTXO reference
            utxo_ref = UTXOReference(
                txid=data['txid'],
                vout=int(data['vout']),
                amount=float(data['amount'])
            )
            
            # Create token based on type
            if token_type == TokenType.FUNGIBLE:
                token = FungibleToken(
                    name=data['name'],
                    description=data.get('description'),
                    token_type=token_type,
                    wallet_name=data['wallet_name'],
                    utxo_ref=utxo_ref,
                    total_supply=int(data['total_supply']),
                    decimals=int(data.get('decimals', 18))
                )
            else:
                token = NonFungibleToken(
                    name=data['name'],
                    description=data.get('description'),
                    token_type=token_type,
                    wallet_name=data['wallet_name'],
                    utxo_ref=utxo_ref,
                    token_id=data['token_id'],
                    metadata_uri=data.get('metadata_uri')
                )
            
            db.store_token(token)
            flash('Token created successfully')
            return redirect(url_for('tokens'))
            
        except Exception as e:
            logger.error(f"Error creating token: {str(e)}")
            flash(f'Error creating token: {str(e)}')
            
    return render_template('create_token.html')

# Batch Operations Routes
@app.route('/batch', methods=['GET', 'POST'])
@login_required
def batch_operations():
    if request.method == 'POST':
        try:
            file = request.files['batch_file']
            if file:
                # Save file temporarily
                temp_path = os.path.join('/tmp', file.filename)
                file.save(temp_path)
                
                # Process batch
                operation = batch_processor.load_batch_file(temp_path)
                result = batch_processor.process_batch(operation)
                
                # Clean up
                os.remove(temp_path)
                
                return jsonify(result)
        except Exception as e:
            logger.error(f"Error processing batch: {str(e)}")
            return jsonify({"error": str(e)}), 400
            
    return render_template('batch.html')

# Backup Routes
@app.route('/backups')
@login_required
def backups():
    backup_list = backup_manager.list_backups()
    return render_template('backups.html', backups=backup_list)

@app.route('/backups/create', methods=['POST'])
@login_required
def create_backup():
    try:
        description = request.form.get('description')
        backup_path = backup_manager.create_backup(description)
        return jsonify({"path": backup_path})
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/backups/restore', methods=['POST'])
@login_required
def restore_backup():
    try:
        backup_path = request.form.get('backup_path')
        success = backup_manager.restore_backup(backup_path)
        return jsonify({"success": success})
    except Exception as e:
        logger.error(f"Error restoring backup: {str(e)}")
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True) 