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
    print(type(accounts[0]))
    algod_client:AlgodClient = sandbox.get_algod_client()
    addr = accounts[0].address
    sk = accounts[0].private_key

    app = Ecommerce()
    app_client = client.ApplicationClient(algod_client,app,signer=AccountTransactionSigner(sk))
    app_addr = ""
    _USDC_SUPPLY = 446744073709
    _USDC_DECIMALS = 6

    tokens = []
    @pytest.fixture
    def admin_acc(self) -> tuple[str,str,AccountTransactionSigner]:
        addr, sk = self.accounts[0].address, self.accounts[0].private_key
        return (addr,sk,self.accounts[0].signer)
    @pytest.fixture
    def seller_acc(self) -> tuple[str,str,AccountTransactionSigner]:
        addr, sk = self.accounts[1].address, self.accounts[1].private_key
        return (addr,sk,self.accounts[1].signer)
    @pytest.fixture
    def buyer_acc(self) -> tuple[str,str,AccountTransactionSigner]:
        addr, sk = self.accounts[2].address, self.accounts[2].private_key
        return (addr,sk,self.accounts[2].signer)

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
        # others acoount opt-in
        stxn = transaction.AssetOptInTxn(saddr,sp,r['asset-index'])
        self.algod_client.send_transaction(stxn.sign(ssk))
        stxn = transaction.AssetOptInTxn(baddr,sp,r['asset-index'])
        self.algod_client.send_transaction(stxn.sign(bsk))

        # other acc receiving usdc
        txn = transaction.AssetTransferTxn(
            addr,
            sp,
            baddr,
            100000,
            r['asset-index']
        )
        self.algod_client.send_transaction(txn.sign(sk))
        txn = transaction.AssetTransferTxn(
            addr,
            sp,
            saddr,
            100000,
            r['asset-index']
        )
        self.algod_client.send_transaction(txn.sign(sk))

        return r['asset-index']

    def test_app_create(self):
        self.app,self.app_addr,_ = self.app_client.create()
        app_state = self.app_client.get_application_state()
        sender = self.app_client.get_sender()

        assert app_state[Ecommerce.admin.str_key()] == decode_address(sender).hex(), "The admin should be the first address"
        assert self.app_client.app_id > 0, "No app id created"

    def test_setup(self,create_usdc: int):
        usdc = create_usdc
        self.tokens.append(usdc)
        sp = self.algod_client.suggested_params()
        ptxn = TransactionWithSigner(
            txn = transaction.PaymentTxn(
                self.app_client.get_sender(), sp, self.app_client.app_addr,int(1e7)
            ),
            signer = self.app_client.get_signer(),
        )
        r = self.app_client.call(self.app.setup,t = ptxn)
        app_state = self.app_client.get_application_state()
        # assert app_state["t"] == usdc, "Token for trading must be usdc"

        assert r.return_value == "setup_successfull", "Application must str message"
    def test_opt_token(self):
        sp = self.algod_client.suggested_params()
        ptxn = TransactionWithSigner(
            txn = transaction.PaymentTxn(
                self.app_client.get_sender(), sp, self.app_client.app_addr,int(1e7)
            ),
            signer = self.app_client.get_signer(),
        )
        r = self.app_client.call(self.app.addToken,a = self.tokens[0])
        print("### contract opt-in asset")
        print(r.return_value)

    def test_seller_opt_in(self,seller_acc:tuple[str,str,AccountTransactionSigner]):
        addr,sk,signer =  seller_acc
        app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=signer)
        r = app_client.opt_in()
        client_state = app_client.get_account_state()


        # assert client_state[Ecommerce.deposit.str_key()] == 0, "The initial deposit must be zero"
        # assert client_state[Ecommerce.is_seller.str_key()] == 0, "The the account can't be a seller by default"


    def test_buyer_opt_in(self,buyer_acc:tuple[str,str,AccountTransactionSigner]):
        addr,sk,signer =  buyer_acc
        app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=signer)
        r = app_client.opt_in()
        client_state = app_client.get_account_state()

    def test_become_seller(self,seller_acc: tuple[str,str,AccountTransactionSigner]):
        addr,sk,signer =  seller_acc
        app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=signer)
        sp = self.algod_client.suggested_params()
        ptxn = TransactionWithSigner(
            txn = transaction.PaymentTxn(
                addr, sp, self.app_client.app_addr,int(4e3)
            ),
            signer = signer
        )
        r = app_client.call(self.app.setSeller,p = ptxn)
        app_state = app_client.get_account_state()
        assert app_state["is_seller"] == 1, "After paying the cost, the value of is_seller must be 1"
        assert r.return_value == 1, "Application must return 1"


    # def test_get_deposit(self,
    #                      buyer_acc:tuple[str,str,AccountTransactionSigner]):
    #     baddr,bsk,bs = buyer_acc
    #     app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=bs)
    #     sp = self.algod_client.suggested_params()
    #     app_state = app_client.get_application_state()
    #     asset_id = self.tokens[0]

    #     # asset_id = app_state[Ecommerce.token.str_key()]
    #     r = app_client.call(
    #         Ecommerce.getDeposit,
    #         addr = baddr,
    #         i = 0)
    #     print(r.return_value)

    def test_make_order(self,

                        seller_acc:tuple[str,str,AccountTransactionSigner],
                        buyer_acc:tuple[str,str,AccountTransactionSigner]):
        baddr,bsk,bs = buyer_acc
        saddr,_,_ = seller_acc
        app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=bs)
        sp = self.algod_client.suggested_params()
        app_state = app_client.get_application_state()
        asset_id = self.tokens[0]

        # asset_id = app_state[Ecommerce.token.str_key()]
        r = app_client.call(
            Ecommerce.placeOrder,
            oracle_pay = TransactionWithSigner(
                txn=transaction.PaymentTxn(baddr,sp,self.app_client.app_addr,1000,note="paying for the oracle"),
                signer=bs
            ),
            product_pay = TransactionWithSigner(
                txn=transaction.AssetTransferTxn(baddr,sp,self.app_client.app_addr,2000,asset_id),
                signer=bs
            ),
            token_ = asset_id
        )
        local_state = app_client.get_account_state()
        assert r.return_value == 1, "Application must return 1"


    def test_oracle_order_success(self,
                                  seller_acc:tuple[str,str,AccountTransactionSigner],
                                  buyer_acc:tuple[str,str,AccountTransactionSigner]):
        saddr,_,_ = seller_acc
        baddr,bsk,bs = buyer_acc
        order = {"seller": baddr, "order_id": "xx1","amount":1,"token":2002, "status":0 }
        sp = self.algod_client.suggested_params()

        r = self.app_client.call(
            Ecommerce.oPlaceOrderSuccess,
            acc=baddr,
            order=order,
            i=1,
            d={"token_id": self.tokens[0],"amount":10000},
        )
        print(r.return_value)
        # assert r.return_value == order["order_id"], "Application must return 1"

    def test_get_deposit_after(self,
                         buyer_acc:tuple[str,str,AccountTransactionSigner]):
        baddr,bsk,bs = buyer_acc
        app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=bs)
        sp = self.algod_client.suggested_params()


        # asset_id = app_state[Ecommerce.token.str_key()]
        r = app_client.call(
            Ecommerce.getDeposit,
            addr = baddr,
            i = 1)
        print(r.return_value)

    def test_oracle_order_success_2(self,
                                    seller_acc:tuple[str,str,AccountTransactionSigner],
                                    buyer_acc:tuple[str,str,AccountTransactionSigner]):
        saddr,_,_ = seller_acc
        baddr,bsk,bs = buyer_acc
        order = {"seller": saddr, "order_id": "xx2","amount":1,"token":2002,"status": 0}
        sp = self.algod_client.suggested_params()


        r = self.app_client.call(
            Ecommerce.oPlaceOrderSuccess,
            acc=baddr,
            order=order,
            i=0,
            d={"token_id": self.tokens[0],"amount":12340},
        )
        print(r.return_value)


    # def test_accept_order(self,
    #                       seller_acc:tuple[str,str,AccountTransactionSigner],
    #                       buyer_acc:tuple[str,str,AccountTransactionSigner]):
    #     baddr,bsk,bs = buyer_acc
    #     saddr,_,ss = seller_acc
    #     app_client = client.ApplicationClient(self.algod_client,self.app,self.app_client.app_id,signer=ss)
    #     sp = self.algod_client.suggested_params()
    #     app_state = app_client.get_application_state()

    #     r = app_client.call(
    #         Ecommerce.acceptOrder,
    #         b=baddr,
    #         order_id="xx2",
    #     )
    #     print(r.return_value)
