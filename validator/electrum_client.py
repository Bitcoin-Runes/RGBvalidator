import ssl
import json
import socket
from typing import Any, Dict, Optional

class ElectrumClient:
    def __init__(self, host: str, port: int, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.socket: Optional[socket.socket] = None
        self.request_id = 0

    def connect(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.use_ssl:
                context = ssl.create_default_context()
                self.socket = context.wrap_socket(sock, server_hostname=self.host)
            else:
                self.socket = sock
            
            self.socket.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def send_request(self, method: str, params: list) -> Dict[str, Any]:
        if not self.socket:
            raise ConnectionError("Not connected to server")

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id
        }
        
        self.socket.send(json.dumps(request).encode() + b'\n')
        response = self.socket.recv(1024).decode()
        return json.loads(response)

    def get_transaction(self, txid: str) -> Dict[str, Any]:
        return self.send_request("blockchain.transaction.get", [txid])

    def is_connected(self) -> bool:
        return self.socket is not None 