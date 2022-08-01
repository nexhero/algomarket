from pyteal import *
from typing import Final
from beaker import (
    Application,
    update,
    create,
    opt_in,
    AccountStateValue,
    ApplicationStateValue,
    Authorize,
    external,
    internal,
    client,
    consts
)

__USDC_ID : int
"""Define the usdc asset in the mainnet"""
__USDC_ID = 98_430_563

class Ecommerce(Application):
    """This smartcontract worsk as escrow between buyer and sellers, is the main point entrace to make request
    to the oracle."""

    #################################################
    # DEFINE ALL GLOBAL STATE FOR THE SMARTCONTRACT #
    #################################################

    admin: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type = TealType.bytes,
        default=Global.creator_address(),
        descr="The address that can administrate the smartcontract."
    )
    """Define who can administrate the smartcontract"""

    oracle: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        descr="The oracle address that receive all the request."
    )
    """Define the oracle address."""

    earnig: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Acomulate the fees that smartcontract made for selling products"
    )
    """Manage the earning that smartcontract made when a seller sell a product."""

    comission_fees: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default=Int(1000),
        descr="Store the fees that seller pay for selling products"
    )
    """This is the percent that seller pay for selling products"""

    oracle_fees: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default = Int(10000),
        descr="Store the fees that all user pay for making request to the oracle."
    )
    """The cost for making request to the oracle"""

    seller_insurance: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default = Int(1000),
        descr="If an user become a seller, it must pay some algos, the amount of algo deposited is used to insurance the seller,"
    )
    """Cost for becoming a seller, this algos will use as insurance."""

    premium_cost: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default = Int(100000),
        descr="The price that seller must pay to become a premium seller, this will reduce the comission fees."
    )
    """Define the cost for a seller to become a premium, by doing this, seller receive a discont on sell comission."""


    ################################################
    # DEFINE ALL LOCAL STATE FOR THE SMARTCONTRACT #
    ################################################

    deposit: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default = Int(0),
        descr="Usdc currently deposit for the buyer user."
    )
    """Current usdc buyer deposited."""
    income: Final[AccountStateValue] =AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="USDC currently for the seller user."
    )
    """Available usdc for the seller."""
    is_seller: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Flag, is the address a seller user."
    )
    """Flag manage is the account is a seller."""
    is_premium: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Address that paid for a premium."
    )
    """Flag manage is the seller paid for a premium service."""

    @update
    def update(self):
        return Seq(
            self.admin.set(Bytes("Random Text")),
            Approve()
        )
    @create
    def create(self):
        """On deploy application."""
        return Seq(
            self.initialize_application_state(),
            self.admin.set(Txn.sender())
            )

    @opt_in
    def opt_in(self):
        """Account registered into the smartcontract"""
        return self.initialize_account_state()

    @internal(TealType.uint64)
    def isAdminAddr(self):
        """Check if the sender is the administrator for the smarcontract."""
        return If( Txn.sender() == self.admin, Return(Int(1)),Return(Int(0)))

    @internal(TealType.uint64)
    def isOracleAddr(self):
        """Check if the sender is the oracle address"""
        return If(Txn.sender() == self.oracle, Return(Int(1)),Return(Int(0)))

    @internal(TealType.uint64)
    def isPremiumSeller(self):
        """Check if the sender is a premium seller account"""
        return self.is_premium

    @external
    def setPremium(self,p: abi.PaymentTransaction,*,output: abi.Uint64):
        """Set a seller as premium user"""
        return Seq(
            Assert(
                self.isPremiumSeller() == Int(0),
                Global.group_size() == Int(2),
                p.get().receiver() == Global.current_application_address(),
                p.get().amount() >= self.premium_cost

            ),
            output.set(Int(1)),
        )
    @external
    def setSeller(self,p: abi.PaymentTransaction,*,output: abit.Uint64):
        """Pay some algos and become a seller, the algos goes to the insured amount"""
        return Seq(
            Assert(
                Global.group_size() == Int(2),
                p.get().receiver() == Global.current_application_address(),
                p.get().amount() >= self.seller_insurance,
            ),
            output.set(Int(1))
        )

    @internal(TealType.none)
    def withdrawUSDC(self, addr, amt):
        """Move USDC token to an address"""
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: aid,
                    TxnField.asset_amount: amt,
                    TxnField.asset_receiver: addr,
                }
            ),
            InnerTxnBuilder.Submit(),
        )



if __name__ == "__main__":
    from algosdk.atomic_transaction_composer import AccountTransactionSigner, TransactionWithSigner
    from algosdk import account, encoding, mnemonic, future
    from beaker import sandbox, client, Application

    admin = "season purchase grape abstract donkey dinner field judge piece trick garlic usage present man suffer there into crawl regret toast festival liar police abandon smooth"
    admin_pk = mnemonic.to_public_key(admin)
    admin_sk = mnemonic.to_private_key(admin)

    seller = "unfair gold proud cradle raw unknown nominee zebra alley habit ready joke impact type solution valid exile arrange tilt camera gather sausage weather absorb prepare"
    seller_pk = mnemonic.to_public_key(seller)
    seller_sk = mnemonic.to_private_key(seller)

    signer = AccountTransactionSigner(admin_sk)
    app = Ecommerce()
    algod_client = sandbox.get_client()
    app_client = client.ApplicationClient(algod_client,app,15,signer=signer)

    sp = app_client.client.suggested_params()
    ptxn = TransactionWithSigner(
        txn=future.transaction.PaymentTxn(
            admin_pk,sp,seller_pk,amt=100000
        ),
        signer=signer,
    )


    # app_id, app_addr, txid = app_client.create()
    # print(f"Created App with id: {app_id} and address addr:{app_addr} in tx:{txid}")
    # r = app_client.opt_in()
    print("Updating App...")
    r = app_client.update()
    print(r)
    print("----")
    # r = app_client.call(app.setPremium,p=ptxn)
    # print(r.return_value)
    # r = app_client.call(app.setAdminAddr)
    # print(f"Set new admin:{r.return_value}")
    # r = app_client.call(app.getAdminAddr)
    # print(f"The admin addr is:{r.return_value}")
    # is_admin = app_client.call(app.isAddrAdmin)
    # print(f"sender is admin?:{is_admin.return_value}")
    #
