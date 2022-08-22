from pyteal import *
from typing import Final
from beaker import (
    Application,
    update,
    create,
    opt_in,
    AccountStateValue,
    DynamicAccountStateValue,
    ApplicationStateValue,
    DynamicApplicationStateValue,
    Authorize,
    external,
    internal,
    client,
    consts,


)


class Ecommerce(Application):
    """This smartcontract worsk as escrow between buyer and sellers, is the main point entrace to make request
    to the oracle."""
    # TODO: all the external function return a message

    _oracle_fees = 1000
    """Default oracle fees cost"""
    _comission_fees = 1000
    """Default comission for sellers"""
    _seller_cost = 4000
    """Default cost to be a seller"""
    __ORDER_LIST_MAX = 7

    # Define status for the orders
    ORDER_PENDING = 0
    ORDER_ACCEPTED = 1
    ORDER_CANCELLED = 2
    ORDER_COMPLETED = 3

    ###########################################
    # DEFINE STRUCTURES FOR THE SMARTCONTRACT #
    ###########################################


    class Order(abi.NamedTuple):
        """
        Define the order structure, this store the current bussines for the buyer.
        """
        seller: abi.Field[abi.Address]     # The address should by encrypted to protect buyer privacy.
        order_id: abi.Field[abi.String]    # The order id should by encrypted to proect buyer privacy.
        amount: abi.Field[abi.Uint64]
        token: abi.Field[abi.Uint64]
        status: abi.Field[abi.Uint8]


    #################################################
    # DEFINE ALL GLOBAL STATE FOR THE SMARTCONTRACT #
    #################################################

    admin: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type = TealType.bytes,
        default=Global.creator_address(),
        descr="The address that can administrate the smartcontract."
    )
    """Define who can administrate the smartcontract"""

    oracle_address: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        key=Bytes("o"),
        default=Global.creator_address(),
        descr="The oracle address that receive all the request."
    )
    """Define the oracle address."""

    ealgos: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default = Int(0)
    )
    """Count earning made in algos."""
    eusdc: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default = Int(0)
    )
    """Count earning made in usdc."""

    eusdt: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.uint64,
        default = Int(0)
    )
    """Count earning made in usdt."""

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
        # TODO: change variable name
        stack_type=TealType.uint64,
        key=Bytes("si"),
        default = Int(_seller_cost),
        descr="If an user become a seller, it must pay some algos, the amount of algo deposited is used to insurance the seller,"
    )
    """Cost for becoming a seller, this algos will use as insurance."""

    ################################################
    # DEFINE ALL LOCAL STATE FOR THE SMARTCONTRACT #
    ################################################

    ###################
    # BUYER VARIABLES #
    ###################
    dalgo: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )
    dusdc: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )
    dusdt: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )
    dmy_token: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )

    orders: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=__ORDER_LIST_MAX,
        descr="Current order posted by the buyer."
    )
    """List of orders posted by the buyer."""

    order_index: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0),
        key=Bytes("oi"),
        descr = "Manage the current index for the order list array"
    )
    """Manage the current key position for the orders"""

    ####################
    # SELLER VARIABLES #
    ####################
    ialgo: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )
    iusdc: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )
    iusdt: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
    )
    imy_token: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0)
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
        return self.acct_state.initialize()
        return self.initialize_account_state()

    @internal(TealType.uint64)
    def isAdmin(self):
        """Check if the sender is the administrator for the smarcontract."""
        return Or(
            Txn.sender() == self.admin,
            Txn.sender() == self.oracle_address
        )

        # return If( Txn.sender() == self.admin, Return(Int(1)),Return(Int(0)))

    @external(authorize=Authorize.only(Global.creator_address()))
    def addToken(self,
                 a: abi.Asset,
                 *, output:abi.String):
        """Enable new tokens for payment"""
        return Seq(
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: a.asset_id(),
                    TxnField.asset_amount: Int(0),
                    TxnField.asset_receiver: self.address,
                }
            ),
            InnerTxnBuilder.Submit(),
            output.set("new_token_added")
        )

    @external(authorize=Authorize.only(Global.creator_address()))
    def setup(self,
              t: abi.PaymentTransaction,
              *,output:abi.String):
        """The contract receive some algos and opt-in into the token to use for trading."""
        return Seq(
            Assert(
                t.get().receiver() == self.address
            ),
            output.set("setup_successfull")
        )

    @internal(TealType.uint64)
    def isOracleAddr(self):
        """Check if the sender is the oracle address"""
        return If(Txn.sender() == self.oracle_address, Return(Int(1)),Return(Int(0)))

    @internal(TealType.uint64)
    def isSeller(self):
        """Check if the address called is a seller account."""
        # TODO: Check is the seller hold the nft
        return Int(1)

    @external
    def addDepositUsdc(
            self,
            acct: abi.Account,
            amt: abi.Uint64
        ):
        # TODO: only admin or the oracle  can do this
        #
        return Seq(
            Assert(
                self.isAdmin() == Int(1)
            ),
            self.dusdc[acct.address()].increment(amt.get())
        )
    @external
    def addDepositAlgo(
            self,
            acct: abi.Account,
            amount: abi.Uint64
        ):
        return Seq(
            Assert(
                self.isAdmin() == Int(1)
            ),
            self.dalgo[acct.address()].increment(amount.get())
        )

    @external(read_only=True)
    def getDepositUsdc(self,acct: abi.Account,*,output: abi.Uint64):
        """Get deposit for a specific token using the index"""
        return Seq(
            output.set(self.dusdc[acct.address()]),

        )

    @external(read_only=True)
    def getDepositAlgo(self,acct: abi.Account,*,output: abi.Uint64):
        """Get deposit for a specific token using the index"""
        return Seq(
            output.set(self.dalgo[acct.address()]),
        )
    @external(read_only=True)
    def getIncomeUsdc(self,addr: abi.Account,*,output: abi.Uint64):
        """Get income for a specific token using the index"""
        return Seq(
            output.set(self.iusdc[addr.address()]),
        )

    @external(read_only=True)
    def getIncomeAlgo(self,acct: abi.Account,*,output: abi.Uint64):
        """Get income for a specific token using the index"""
        return Seq(
            output.set(self.ialgo[acct.address()]),
        )

    @external(read_only=True)
    def getCurrentIndex(
            self,
            acct: abi.Account,
            *, output: abi.Uint64):
        return output.set(self.order_index[acct.address()])

    @external(read_only=True)
    def getOrderIndex(
            self,
            i: abi.Uint8,
            acct: abi.Account,
            *, output: abi.String):
        # TODO: Error when using read_only
        return output.decode(self.orders[i][acct.address()])

    @external(authorize=Authorize.only(Global.creator_address()))
    def setOrderIndex(
            self,
            i: abi.Uint8,       # The index to store
            o: Order,           # The order
            acct: abi.Account,   # Store to this address
            ):
        return Seq(
            Assert(
                self.isAdmin() == Int(1)
            ),
            self.orders[i][acct.address()].set(o.encode())
        )

    @internal(TealType.uint64)
    def searchOrderIndex(self,acct,order_id: abi.String):
        """
        Check if the account has the order on his list, and return the index,
        Return 0 if doesn't has the order, otherwise return the index + 1,
        because pyteal do not support negative numbers.
        """
        idx = abi.make(abi.Uint8)
        i = ScratchVar(TealType.uint64)
        r = ScratchVar(TealType.uint64) # the return value
        return Seq(
            r.store(Int(0)),
            For(i.store(Int(0)), i.load() < self.order_index[acct], i.store(i.load() + Int(1))).Do(
                    idx.set(i.load()),
                    (_order := self.Order()).decode(self.orders[idx][acct]),
                    (_order_id := abi.String()).set(_order.order_id),
                    If(_order_id.get() == order_id.get())
                    .Then(
                        r.store(i.load()+Int(1))
                    )
            ),
            Return(r.load())
        )

    @external
    def oPostOrderUsdc(self,
                       acct: abi.Account,
                       amt: abi.Uint64,
                       o: Order,
                       ):
        i = abi.make(abi.Uint8)
        """The oracle validated the order, and if using usdc token call this method"""
        return Seq(
            Assert(
                self.isAdmin() == Int(1),
            ),
            i.set(self.order_index[acct.address()]),
            self.orders[i][acct.address()].set(o.encode()), # Store the order in the array
            self.dusdc[acct.address()].increment(amt.get()), # increment the balance in usdc tokens
            self.order_index[acct.address()].increment(Int(1)), # update for the next index

        )

    @external
    def placeOrderToken(self,
                   oracle_pay:abi.PaymentTransaction,
                   product_pay:abi.AssetTransferTransaction,
                   token_:abi.Asset,
                   *,output: abi.Uint16):
        """
        The buyer send tokens for paying the products and some algos for the oracle service.
        The oracle will check the transacion and validate the payment, if there is something
        wrong with it, the oracle will send back the tokens to the buyer.
        Otherwise, it will create the order to the seller.
        """
        return Seq(
            # Verify inputs
            Assert(
                # validate de payment to the oracle
                oracle_pay.get().amount() >= self.oracle_fees,
                oracle_pay.get().receiver() == Global.current_application_address(),

                product_pay.get().asset_receiver() == self.address,
                # product_pay.get().xfer_asset() == self.token,
                product_pay.get().asset_amount() >= Int(0),
            ),

            output.set(Int(1))
        )


    @external
    def takeOrder(self,
                    acct: abi.Account,
                    order_id: abi.String,
                    *,
                    output: abi.String
                    ):
        """
        The seller accept the order request from the buyer,
        and increase the deposit on the seller account.
        """
        r = abi.make(abi.Uint8)            # Return value for teh search
        i = abi.make(abi.Uint8)            # Real index
        s = abi.make(abi.Uint8)
        return Seq(
            Assert(
                self.isSeller() == Int(1),
            ),
            r.set(self.searchOrderIndex(acct.address(),order_id)),
            If(r.get() != Int(0))
            .Then(
                # Found the order, now it process to check the seller address
                i.set(r.get()-Int(1)),
                (_order := self.Order()).decode(self.orders[i][acct.address()]),
                (seller := abi.Address()).set(_order.seller),
                If(seller.get() != Txn.sender())
                .Then(
                    # output.set("sender_is_not_the_seller")     # The sender is not the seller for this order.
                    output.set("sender_is_not_the_seller_order")
                )
                .Else(
                    (order_id := abi.String()).set(_order.order_id),
                    (amount := abi.Uint64()).set(_order.amount),
                    (token := abi.Uint64()).set(_order.token),
                    (status := abi.Uint8()).set(_order.status),

                    Assert( status.get() == Int(0)),

                    status.set(self.ORDER_ACCEPTED),
                    _order.set(seller,order_id,amount,token,status),
                    self.orders[i][acct.address()].set(_order.encode()),

                    (_order := self.Order()).decode(self.orders[i][acct.address()]),
                    output.set("status_order_updated")
                )
            )
            .Else(
                # The order was not found, return 0
                output.set("order_not_found"),
            ),
        )
