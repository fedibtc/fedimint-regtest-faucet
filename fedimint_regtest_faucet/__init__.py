import os
import requests
import random
import json

from flask_qrcode import QRcode
from flask import Flask, render_template, request, jsonify
from lightning import LightningRpc

ln_rpc = LightningRpc(os.environ['CLN_RPC_SOCKET'])
app = Flask(__name__)
QRcode(app)

connect_str = os.environ['FM_CONNECT_STRING']
BITCOIND_URL = os.environ['BITCOIND_URL']
BITCOIND_USER = os.environ['BITCOIND_USER']
BITCOIND_PASSWORD = os.environ['BITCOIND_PASSWORD']
bind_addr = os.environ.get('FAUCET_BIND_ADDR', '::1')

def btc_rpc(method, params=[]):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "minebet",
        "method": method,
        "params": params
    })
    return requests.post(BITCOIND_URL, auth=(BITCOIND_USER, BITCOIND_PASSWORD), data=payload).json()

def block_height():
    return btc_rpc("getblockchaininfo")["result"]["blocks"]

def new_address():
    return btc_rpc("getnewaddress")["result"]

def mine_blocks(num_blocks):
    address = new_address()
    return btc_rpc("generatetoaddress", params=[num_blocks, address])

def send_bitcoin(address, amount_sats):
    amount_btc_str = '%.8f' % (amount_sats / 100_000_000)
    return btc_rpc("sendtoaddress", params=[address, amount_btc_str])

def get_txoutproof(txid):
    app.logger.info(btc_rpc("gettxoutproof", params=[[txid]]))
    return btc_rpc("gettxoutproof", params=[[txid]])["result"]

def get_tx(txid):
    return btc_rpc("gettransaction", params=[txid])["result"]["hex"]

@app.route('/', methods=['GET', 'POST'])
def index():
    invoice = None
    new_addr = None
    pay_result = None
    error = None

    if request.method == 'POST':
        # mint blocks (must be first because it also has an amount ...)
        if 'address' in request.form:
            address = request.form['address']
            if (address.startswith("bitcoin:")):
                address = address.split(':')[1]
            send_bitcoin(address, int(request.form["amount"]))

        # create invoice
        elif 'amount' in request.form:
            # convert to sats
            amount = int(request.form['amount']) * 1000
            invoice = ln_rpc.invoice(amount, str(random.random()), 'test')['bolt11']

        # pay invoice
        elif 'invoice' in request.form:
            invoice = request.form['invoice']
            if (invoice.startswith("lightning:")):
                invoice = invoice.split(':')[1]
            try:
                pay_result = str(ln_rpc.pay(invoice))
            except Exception as e:
                error = e

        # mint blocks
        elif 'blocks' in request.form:
            mine_blocks(int(request.form["blocks"]))

        # generate address
        else:
            new_addr = new_address()

    height = block_height()

    return render_template('index.html', name='justin',
        invoice=invoice, pay_result=pay_result, connect_str=connect_str, height=height, address=new_addr, error=error)

@app.route('/proof/<txid>')
def proof(txid):
    proof = get_txoutproof(txid)
    # tx = get_tx(txid)
    # return jsonify({"proof": proof, "tx": tx})
    app.logger.info(proof)
    return proof

@app.route('/pay-invoice', methods=["POST"])
def pay_invoice():
    app.logger.info("pay-invoice")
    json = request.get_json()
    app.logger.info("/pay-invoice json %s", json)
    try:
        pay_result = str(ln_rpc.pay(json['invoice']))
        return jsonify(pay_result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate-invoice', methods=["POST"])
def generate_invoice():
    json = request.get_json()
    try:
        invoice = ln_rpc.invoice(json["amount"], str(random.random()), 'test')['bolt11']
        return jsonify({"invoice": invoice})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/webln', methods=['GET', 'POST'])
def webln():
    return render_template('webln.html')


def run():
    app.run(host=bind_addr)