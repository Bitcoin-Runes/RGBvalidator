import ssl
import json
import socket
import logging
import time
from typing import Any, Dict, Optional, List
from decimal import Decimal

class ElectrumClient:
    """Client for connecting to Electrum servers"""
    
    def __init__(self, host: str, port: int, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.socket = None
        self.request_id = 0
        self.last_request_time = 0
        self.reconnect_interval = 1  # seconds
        self.max_retries = 3
        self.connection_timeout = 30  # seconds
        self.operation_timeout = 60  # seconds
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with appropriate settings"""
        # Use a more permissive SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.verify_mode = ssl.CERT_NONE
        context.check_hostname = False
        # Enable all available protocols
        context.options &= ~ssl.OP_NO_TLSv1
        context.options &= ~ssl.OP_NO_TLSv1_1
        context.options &= ~ssl.OP_NO_TLSv1_2
        context.options &= ~ssl.OP_NO_TLSv1_3
        # Set broader cipher suite
        context.set_ciphers('DEFAULT')
        return context

    def connect(self) -> bool:
        """Connect to the Electrum server with improved error handling"""
        try:
            # Clean up any existing connection
            self.close()
            
            # Create socket with longer timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connection_timeout)
            
            if self.use_ssl:
                context = self._create_ssl_context()
                # Wrap socket with error handling
                try:
                    self.socket = context.wrap_socket(sock, server_hostname=self.host)
                except ssl.SSLError as e:
                    self.logger.error(f"SSL error during wrap: {str(e)}")
                    sock.close()
                    return False
            else:
                self.socket = sock

            # Connect with timeout and error handling
            try:
                self.socket.connect((self.host, self.port))
            except socket.error as e:
                self.logger.error(f"Connection error: {str(e)}")
                self.close()
                return False

            self.socket.settimeout(self.operation_timeout)

            # Initialize protocol with version negotiation and error handling
            try:
                # Try different protocol versions
                for version in ['1.4', '1.2', '1.1']:
                    try:
                        version_info = self._send_request_raw('server.version', 
                            ['electrum-client', version], 
                            timeout=10)
                        if version_info:
                            self.logger.info(f"Connected to Electrum server: {version_info}")
                            return True
                    except Exception as e:
                        self.logger.warning(f"Failed protocol version {version}: {str(e)}")
                        continue
                
                self.logger.error("Failed all protocol versions")
                return False
                
            except Exception as e:
                self.logger.error(f"Protocol negotiation failed: {str(e)}")
                self.close()
                return False

        except Exception as e:
            self.logger.error(f"Failed to connect to Electrum server: {str(e)}")
            self.close()
            return False

    def _send_request_raw(self, method: str, params: List[Any], timeout: int = None) -> Any:
        """Send a raw request to the server with improved error handling"""
        if not self.socket:
            raise Exception("Not connected to server")

        if timeout is None:
            timeout = self.operation_timeout

        try:
            self.request_id += 1
            request = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self.request_id
            }

            # Send request with timeout
            request_data = json.dumps(request).encode() + b'\n'
            self.socket.settimeout(timeout)
            bytes_sent = 0
            while bytes_sent < len(request_data):
                sent = self.socket.send(request_data[bytes_sent:])
                if sent == 0:
                    raise Exception("Socket connection broken")
                bytes_sent += sent

            # Read response with timeout
            response = b''
            start_time = time.time()
            
            while b'\n' not in response:
                if time.time() - start_time > timeout:
                    raise Exception("Response timeout")
                
                try:
                    chunk = self.socket.recv(4096)
                    if not chunk:
                        if not response:
                            raise Exception("Connection closed by server")
                        break
                    response += chunk
                except socket.timeout:
                    raise Exception("Response timeout")
                except ssl.SSLError as e:
                    if 'record layer failure' in str(e):
                        # Retry on SSL record layer failure
                        time.sleep(0.1)
                        continue
                    raise

            # Parse response with error handling
            try:
                response_data = json.loads(response.decode())
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to decode response: {response}")
                raise Exception(f"Invalid JSON response: {str(e)}")

            if 'error' in response_data:
                error = response_data['error']
                if isinstance(error, dict):
                    message = error.get('message', 'Unknown error')
                else:
                    message = str(error)
                raise Exception(message)
            
            return response_data.get('result')

        except Exception as e:
            self.logger.error(f"Error in raw request: {str(e)}")
            self.close()
            raise

    def _send_request(self, method: str, params: List[Any] = None, retries: int = None, timeout: int = None) -> Dict[str, Any]:
        """Send a request to the Electrum server with retry logic"""
        if retries is None:
            retries = self.max_retries

        if params is None:
            params = []

        last_exception = None
        for attempt in range(retries):
            try:
                if not self.socket or not self.is_connected():
                    if not self.connect():
                        raise Exception("Failed to connect")
                
                # Rate limiting
                now = time.time()
                if now - self.last_request_time < 0.1:  # Max 10 requests per second
                    time.sleep(0.1)
                self.last_request_time = now

                return self._send_request_raw(method, params, timeout=timeout)

            except Exception as e:
                last_exception = e
                self.logger.error(f"Error sending request (attempt {attempt + 1}/{retries}): {str(e)}")
                self.close()  # Clean up on error
                
                if attempt < retries - 1:
                    time.sleep(self.reconnect_interval * (2 ** attempt))  # Exponential backoff
                    continue
                
                raise last_exception

    def is_connected(self) -> bool:
        """Check if the connection is still alive"""
        if not self.socket:
            return False
        
        try:
            # Try to send a ping
            self._send_request_raw('server.ping', [])
            return True
        except:
            return False

    def get_transaction(self, txid: str) -> Dict[str, Any]:
        """Get transaction by txid"""
        return self._send_request('blockchain.transaction.get', [txid, True])

    def get_transaction_status(self, txid: str) -> Dict[str, Any]:
        """Get transaction status"""
        try:
            merkle = self._send_request('blockchain.transaction.get_merkle', [txid])
            tx = self._send_request('blockchain.transaction.get', [txid, True])
            return {
                'confirmations': merkle.get('confirmations', 0),
                'timestamp': tx.get('time', 0),
                'block_height': merkle.get('block_height'),
                'fee': tx.get('fee', 0)
            }
        except:
            # If merkle request fails, try getting basic transaction info
            tx = self._send_request('blockchain.transaction.get', [txid, True])
            return {
                'confirmations': 0,
                'timestamp': tx.get('time', 0),
                'block_height': None,
                'fee': tx.get('fee', 0)
            }

    def get_block_header(self, block_hash: str) -> Dict[str, Any]:
        """Get block header"""
        try:
            header = self._send_request('blockchain.block.header', [block_hash])
            return self._parse_header(header, block_hash)
        except:
            return self._send_request('blockchain.block.get_header', [block_hash])

    def get_block_header_by_height(self, height: int) -> Dict[str, Any]:
        """Get block header by height"""
        try:
            header = self._send_request('blockchain.block.header', [height])
            return self._parse_header(header)
        except:
            return self._send_request('blockchain.block.get_header', [height])

    def _parse_header(self, header_hex: str, block_hash: str = None) -> Dict[str, Any]:
        """Parse block header hex into a dictionary"""
        try:
            # Try getting parsed header directly
            return self._send_request('blockchain.block.get_header', [block_hash or header_hex])
        except:
            # Fallback to basic parsing
            return {
                'hash': block_hash,
                'timestamp': int(header_hex[8:16], 16),
                'difficulty': int(header_hex[72:80], 16),
                'version': int(header_hex[0:8], 16),
                'size': len(header_hex) // 2
            }

    def get_block_transactions(self, block_hash: str) -> List[str]:
        """Get list of transactions in a block"""
        try:
            return self._send_request('blockchain.block.get_chunk', [block_hash])
        except:
            # Fallback to getting transactions one by one
            txids = []
            height = self.get_block_header(block_hash).get('height')
            if height:
                txids = self._send_request('blockchain.block.get_transaction_ids', [height])
            return txids

    def get_address_history(self, address: str) -> List[Dict[str, Any]]:
        """Get address history"""
        return self._send_request('blockchain.address.get_history', [address])

    def get_address_balance(self, address: str) -> Dict[str, int]:
        """Get address balance"""
        return self._send_request('blockchain.address.get_balance', [address])

    def get_mempool(self) -> List[List[float]]:
        """Get mempool fee histogram"""
        try:
            return self._send_request('mempool.get_fee_histogram', [])
        except:
            # Fallback to empty histogram if not supported
            return []

    def get_fee_estimates(self) -> Dict[int, float]:
        """Get fee estimates for different confirmation targets"""
        estimates = {}
        for target in [1, 2, 4, 6, 12, 24]:
            try:
                fee = self._send_request('blockchain.estimatefee', [target])
                if fee is not None and fee > 0:
                    estimates[target] = fee
            except:
                continue
        return estimates

    def get_headers_count(self) -> int:
        """Get blockchain headers count"""
        try:
            result = self._send_request('blockchain.headers.subscribe', [])
            return result.get('height', 0)
        except:
            # Fallback to getting tip height
            return self.get_current_height()

    def get_current_height(self) -> int:
        """Get current blockchain height"""
        try:
            result = self._send_request('blockchain.headers.subscribe', [])
            return result.get('height', 0)
        except:
            # Fallback method
            tip = self._send_request('blockchain.block.get_tip', [])
            return tip.get('height', 0)

    def close(self):
        """Close the connection with improved cleanup"""
        if self.socket:
            try:
                # Try graceful shutdown first
                try:
                    self.socket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                
                # Always close the socket
                try:
                    self.socket.close()
                except:
                    pass
                
            finally:
                self.socket = None

    def __del__(self):
        """Destructor to ensure connection cleanup"""
        self.close()

    # ... rest of the methods remain the same ... 