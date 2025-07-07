import hashlib
import json
from time import time
from uuid import uuid4
from urllib.parse import urlparse

import requests
from flask import Flask, request, jsonify


class SimpleChain:
    def __init__(self):
        self.transactions = []
        self.chain = []
        self.nodes = set()

        # Create the genesis block
        self.create_block(proof=100, prev_hash='1')

    def create_block(self, proof, prev_hash):
        block = {
            'index': len(self.chain) + 1,
            'timestamp': time(),
            'transactions': self.transactions,
            'proof': proof,
            'previous_hash': prev_hash or self.hash_block(self.chain[-1]),
        }

        self.transactions = []
        self.chain.append(block)
        return block

    def add_transaction(self, sender, recipient, amount):
        self.transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })
        return self.last_block['index'] + 1

    def add_node(self, address):
        parsed = urlparse(address)
        if parsed.netloc:
            self.nodes.add(parsed.netloc)
        elif parsed.path:
            self.nodes.add(parsed.path)
        else:
            raise ValueError('Invalid node address')

    def verify_chain(self, chain):
        prev_block = chain[0]
        idx = 1

        while idx < len(chain):
            current = chain[idx]
            if current['previous_hash'] != self.hash_block(prev_block):
                return False
            if not self.is_valid_proof(prev_block['proof'], current['proof'], self.hash_block(prev_block)):
                return False
            prev_block = current
            idx += 1

        return True

    def resolve_disputes(self):
        # Implements simple consensus: longest valid chain wins
        neighbors = self.nodes
        new_chain = None
        current_length = len(self.chain)

        for node in neighbors:
            try:
                res = requests.get(f'http://{node}/chain')
                if res.status_code == 200:
                    length = res.json()['length']
                    chain = res.json()['chain']
                    if length > current_length and self.verify_chain(chain):
                        current_length = length
                        new_chain = chain
            except requests.RequestException:
                continue

        if new_chain:
            self.chain = new_chain
            return True
        return False

    def proof_of_work(self, last_block):
        prev_proof = last_block['proof']
        prev_hash = self.hash_block(last_block)
        proof = 0

        while not self.is_valid_proof(prev_proof, proof, prev_hash):
            proof += 1

        return proof

    @staticmethod
    def is_valid_proof(last_proof, proof, last_hash):
        guess = f'{last_proof}{proof}{last_hash}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] == "0000"

    @staticmethod
    def hash_block(block):
        # Consistent hashing using ordered keys
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1]


# Flask setup
app = Flask(__name__)
node_id = str(uuid4()).replace('-', '')
blockchain = SimpleChain()


@app.route('/mine', methods=['GET'])
def mine_block():
    last = blockchain.last_block
    proof = blockchain.proof_of_work(last)

    blockchain.add_transaction(sender="0", recipient=node_id, amount=1)
    new_block = blockchain.create_block(proof, blockchain.hash_block(last))

    return jsonify({
        'message': 'Successfully mined a new block.',
        'index': new_block['index'],
        'transactions': new_block['transactions'],
        'proof': new_block['proof'],
        'previous_hash': new_block['previous_hash'],
    }), 200


@app.route('/transactions/new', methods=['POST'])
def create_transaction():
    data = request.get_json()
    required_fields = ['sender', 'recipient', 'amount']

    if not all(field in data for field in required_fields):
        return 'Missing required transaction data', 400

    block_index = blockchain.add_transaction(data['sender'], data['recipient'], data['amount'])
    return jsonify({'message': f'Transaction will be added to block {block_index}'}), 201


@app.route('/chain', methods=['GET'])
def get_chain():
    return jsonify({
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }), 200


@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    data = request.get_json()
    nodes = data.get('nodes')

    if nodes is None:
        return "Error: Please provide a list of node addresses", 400

    for node in nodes:
        blockchain.add_node(node)

    return jsonify({
        'message': 'Nodes registered successfully.',
        'total_nodes': list(blockchain.nodes),
    }), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus_check():
    replaced = blockchain.resolve_disputes()
    if replaced:
        response = {
            'message': 'Replaced with a longer valid chain.',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Current chain is already authoritative.',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='Port to run the node on')
    args = parser.parse_args()

    app.run(host='0.0.0.0', port=args.port)
