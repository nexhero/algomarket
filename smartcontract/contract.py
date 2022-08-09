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


class Ecommerce(Application):
    """This smartcontract worsk as escrow between buyer and sellers, is the main point entrace to make request
    to the oracle."""

    #################################################
    # DEFINE ALL GLOBAL STATE FOR THE SMARTCONTRACT #
    #################################################

    _oracle_fees = 1000
    """Default oracle fees cost"""
    _comission_fees = 1000
    """Default comission for sellers"""
    _premium_cost = 3000
    """Default cost to become a premium seller."""
    _seller_cost = 4000
    """Default cost to be a seller"""

    app_name: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        key=Bytes("app_name"),
        default = Bytes("algomarket"),
        descr="Define the application name for the oracle."
    )
    """Define the application name for the Oracle to reconize the request."""

    admin: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type = TealType.bytes,
        key=Bytes("a"),
        default=Global.creator_address(),
        descr="The address that can administrate the smartcontract."
    )
    """Define who can administrate the smartcontract"""

    token: Final[ApplicationStateValue] = ApplicationStateValue(

        stack_type=TealType.uint64,
        key=Bytes("t"),
        default = Int(0),
        descr="Store the token it will use for transactions, for now just usdc."
    )
    """Token used for trading."""
    oracle: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        key=Bytes("o"),
        default=Global.creator_address(),
        descr="The oracle address that receive all the request."
    )
    """Define the oracle address."""

    earning: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("e"),
        default=Int(0),
        descr="Acomulate the fees that smartcontract made for selling products"
    )
    """Manage the earning that smartcontract made when a seller sell a product."""

    comission_fees: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("cf"),
        default=Int(_comission_fees),
        descr="Store the fees that seller pay for selling products"
    )
    """This is the percent that seller pay for selling products"""

    oracle_fees: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("of"),
        default = Int(_oracle_fees),
        descr="Store the fees that all user pay for making request to the oracle."
    )
    """The cost for making request to the oracle"""

    seller_insurance: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key=Bytes("si"),
        default = Int(_seller_cost),
        descr="If an user become a seller, it must pay some algos, the amount of algo deposited is used to insurance the seller,"
    )
    """Cost for becoming a seller, this algos will use as insurance."""

    premium_cost: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        key = Bytes("pc"),
        default = Int(_premium_cost),
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
        key=Bytes("i"),
        default=Int(0),
        descr="USDC currently for the seller user."
    )
    """Available usdc for the seller."""
    is_seller: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        key=Bytes("is"),
        default=Int(0),
        descr="Flag, is the address a seller user."
    )
    """Flag manage is the account is a seller."""
    is_premium: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        key=Bytes("ip"),
        default=Int(0),
        descr="Address that paid for a premium."
    )
    """Flag manage is the seller paid for a premium service."""

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

    @external(authorize=Authorize.only(Global.creator_address()))
    def setup(self,
              t: abi.PaymentTransaction,
              asset: abi.Asset,
              *,output:abi.Uint64):
        """The contract receive some algos and opt-in into the token to use for trading."""
        return Seq(
            Assert(
                t.get().receiver() == self.address
            ),
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: asset.asset_id(),
                    TxnField.asset_amount: Int(0),
                    TxnField.asset_receiver: self.address,
                }
            ),
            InnerTxnBuilder.Submit(),
            self.token.set(asset.asset_id()),
            output.set(Int(1))
        )

    @internal(TealType.uint64)
    def isOracleAddr(self):
        """Check if the sender is the oracle address"""
        return If(Txn.sender() == self.oracle, Return(Int(1)),Return(Int(0)))

    @internal(TealType.uint64)
    def isSeller(self):
        return self.is_seller

    @internal(TealType.uint64)
    def isPremiumSeller(self):
        """Check if the sender is a premium seller account"""
        return self.is_premium

    @internal(TealType.none)
    def withdrawUSDC(self, addr, amt):
        """Move USDC token to an address"""
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: Int(2), # TODO: Make a global variable to store usdc token id
                    TxnField.asset_amount: amt,
                    TxnField.asset_receiver: addr,
                }
            ),
            InnerTxnBuilder.Submit(),

        )

    @external
    def sellerWithdraw(self,amt: abi.Uint64,*,output: abi.Uint64):
        """A seller make a withdraw of USDC tokens."""
        return Seq(
            Assert(
                self.income >= amt.get()
            ),
            self.withdrawUSDC(Txn.sender(),amt.get()),
            self.income.set(self.income - amt.get()),
            output.set(Int(1))
        )
    @external
    def setPremium(self,p: abi.PaymentTransaction,*,output: abi.Uint64):
        """Set a seller as premium user"""
        return Seq(
            Assert(
                self.isPremiumSeller() == Int(0),
                self.is_seller == Int(1), # Needs to be a seller
                Global.group_size() == Int(2),
                p.get().receiver() == Global.current_application_address(),
                p.get().amount() >= self.premium_cost

            ),
            self.is_premium.set(Int(1)),
            output.set(Int(1)),
        )

    @external
    def setSeller(self,p: abi.PaymentTransaction,*,output: abi.Uint64):
        """Pay some algos and become a seller, the algos goes to the insured amount"""
        return Seq(
            Assert(
                Global.group_size() == Int(2),
                p.get().receiver() == Global.current_application_address(),
                p.get().amount() >= self.seller_insurance,
            ),
            self.is_seller.set(Int(1)),
            output.set(Int(1))
        )

    @external
    def makeOrder(self,
                  oracle_pay:abi.PaymentTransaction,
                  product_pay:abi.AssetTransferTransaction,
                  token_:abi.Asset,
                  *,output: abi.Uint64):

        """
        The buyer send tokens for paying the products and some algos for the oracle service.
        The oracle will check the transacion and validate the payment, if there is something
        wrong with it, the oracle will send back the tokens to the buyer.
        """
        return Seq(
            # Verify inputs
            Assert(
                # validate de payment to the oracle
                oracle_pay.get().amount() >= self.oracle_fees,
                oracle_pay.get().receiver() == self.address, # Must be the oracle address
                # check for the token
                token_.asset_id() == self.token,
                product_pay.get().asset_receiver() == self.address,
                product_pay.get().xfer_asset() == self.token,
                product_pay.get().asset_amount() >= Int(0),
            ),
            self.deposit.increment(product_pay.get().asset_amount()),
            output.set(Int(1))
        )

    @external
    def acceptOrder(self,
                    oracle_pay:abi.PaymentTransaction,
                    buyer_addr: abi.Account,
                    *, output: abi.Uint64):
        """The seller accept the order request from the buyer.
        The oracle will validate the transacction and move the funds from buyer to the seller."""
        return Seq(
            Assert(
                oracle_pay.get().amount() >= self.oracle_fees,
                oracle_pay.get().receiver() == self.address,
                App.localGet(buyer_addr.address(),Bytes("deposit")) > Int(0)

            ),
            output.set(Int(1))
        )
