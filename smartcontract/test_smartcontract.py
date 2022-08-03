from ast import Constant
import pytest
from algosdk.atomic_transaction_composer import *
from algosdk.future import transaction
from algosdk.v2client.algod import AlgodClient
from algosdk.encoding import decode_address
from beaker import client, sandbox
from beaker.client.application_client import ApplicationClient

from .contract import Ecommerce

class TestEcommerce:


    accounts = sandbox.get_accounts()
    algod_client:AlgodClient = sandbox.get_client()
    addr, sk = accounts[0]

    app = Ecommerce()
    app_client = client.ApplicationClient(algod_client,app,signer=AccountTransactionSigner(sk))

    _USDC_SUPPLY = 446744073709
    _USDC_DECIMALS = 6
    @pytest.fixture
    def admin_acc(self) -> tuple[str,str,AccountTransactionSigner]:
        addr, sk = self.accounts[0]
        return (addr,sk,AccountTransactionSigner(sk))
    @pytest.fixture
    def seller_acc(self) -> tuple[str,str,AccountTransactionSigner]:
        addr, sk = self.accounts[1]
        return (addr,sk,AccountTransactionSigner(sk))
    @pytest.fixture
    def buyer_acc(self) -> tuple[str,str,AccountTransactionSigner]:
        addr, sk = self.accounts[2]
        return (addr,sk,AccountTransactionSigner(sk))

    @pytest.fixture
    def create_usdc(self,admin_acc,seller_acc,buyer_acc) -> int:
        addr,sk,signer = admin_acc
        saddr,ssk,ssigner = seller_acc
        baddr,bsk,bsigner = buyer_acc
        sp = self.algod_client.suggested_params()
        txn = transaction.AssetCreateTxn(
            addr,
            sp,
            self._USDC_SUPPLY,
            self._USDC_DECIMALS,
            asset_name="USDC",
            unit_name="tusdc",
            default_frozen=False
        )
        stxn = txn.sign(sk)
        self.algod_client.send_transaction(stxn)
        r = transaction.wait_for_confirmation(self.algod_client,txn.get_txid(),4)
        # stxn = transaction.AssetOptInTxn(saddr,sp,r['asset-index'])
        # self.algod_client.send_transaction(stxn.sign(ssk))
        # stxn = transaction.AssetOptInTxn(baddr,sp,r['asset-index'])
        # self.algod_client.send_transaction(stxn.sign(bsk))
        return r['asset-index']

    def test_app_create(self):
        self.app = self.app_client.create()
        app_state = self.app_client.get_application_state()
        sender = self.app_client.get_sender()
        assert (
            app_state[b"e"] == 0
        ), "Earning should be 0"
        assert app_state[b"a"] == decode_address(sender), "Administrator must be admin_acc"
        assert self.app_client.app_id > 0, "No app id created"

    def test_setup(self,create_usdc: int):
        usdc = create_usdc
        sp = self.algod_client.suggested_params()
        ptxn = TransactionWithSigner(
            txn = transaction.PaymentTxn(
                self.app_client.get_sender(), sp, self.app_client.app_addr,int(1e7)
            ),
            signer = self.app_client.get_signer(),
        )
        r = self.app_client.call(self.app.setup,t = ptxn, asset = usdc)
        app_state = self.app_client.get_application_state()
        assert app_state[b"t"] == usdc, "Token for trading must be usdc"
        assert r.return_value == 1, "Application must return 1"
