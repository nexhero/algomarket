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
    struct,
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
    __ORDER_LIST_MAX = 6
    __TOKEN_LIST_MAX = 4

    # Define status for the orders
    ORDER_PENDING = 0
    ORDER_ACCEPTED = 1
    ORDER_CANCELLED = 2
    ORDER_COMPLETED = 3

    ###########################################
    # DEFINE STRUCTURES FOR THE SMARTCONTRACT #
    ###########################################
    class Tokens(struct.Struct):
        """
        TODO: It need to be implemented.
        This struct is used to manage the tokens deposited for the buyer
        and the incomes for the seller.
        """
        token_id: abi.Uint64           # 0 for algos
        amount: abi.Uint64

    class Order(struct.Struct):
        """
        Define the order structure, this store the current bussines for the buyer.
        """
        seller: abi.Address     # The address should by encrypted to protect buyer privacy.
        order_id: abi.String    # The order id should by encrypted to proect buyer privacy.
        amount: abi.Uint64
        token: abi.Uint64
        status: abi.Uint8


    #################################################
    # DEFINE ALL GLOBAL STATE FOR THE SMARTCONTRACT #
    #################################################

    app_name: Final[ApplicationStateValue] = ApplicationStateValue(
        stack_type=TealType.bytes,
        key=Bytes("app_name"),
        default = Bytes("aMart-SmartContract"),
        descr="Define the application name for the oracle."
    )
    """Define the application name for the Oracle to reconize the request."""

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

    earning: Final[DynamicApplicationStateValue] = DynamicApplicationStateValue(
        # TODO: Implement token structure.
        stack_type=TealType.bytes,
        max_keys = __TOKEN_LIST_MAX,
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
    deposit: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        # TODO: Implement token structure
        stack_type=TealType.bytes,
        max_keys=__TOKEN_LIST_MAX,
        descr="Count deposited tokens"
    )
    """Current usdc buyer deposited."""
    orders: Final[DynamicAccountStateValue] = DynamicAccountStateValue(
        stack_type=TealType.bytes,
        max_keys=__ORDER_LIST_MAX,
        descr="Current order posted by the buyer."
    )
    """List of orders posted by the buyer."""

    order_index: Final[AccountStateValue] = AccountStateValue(
        stack_type = TealType.uint64,
        default = Int(0),
        descr = "Manage the current index for the order list array"
    )
    """Manage the current key position for the orders"""

    ####################
    # SELLER VARIABLES #
    ####################
    income: Final[DynamicAccountStateValue] =DynamicAccountStateValue(
        # TODO: implement token structure
        stack_type=TealType.bytes,
        max_keys = __TOKEN_LIST_MAX,
        descr="Count the income tokens for the seller."
    )
    """Count the income tokens for the seller."""

    is_seller: Final[AccountStateValue] = AccountStateValue(
        stack_type=TealType.uint64,
        default=Int(0),
        descr="Flag, is the address a seller user."
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
        return self.is_seller


    @internal(TealType.bytes)
    def getOrderByIndex(self, on_addr, index: abi.Uint8):
        """Get the value in the orders using the index"""
        # TODO: Validate if the index is out the range
        return self.orders[index][on_addr]

    @internal(TealType.none)
    def setOrderOnIndex(self,on_addr,index:abi.Uint8, value):
        return Seq(self.orders[index][on_addr].set(value))

    @internal(TealType.none)
    def reBlockOrderList(self,on_addr):
        """Move the empty index to the end of the array"""
        # TODO: change the variable i to abi.uint8
        # TODO: temp and next must be abi.String type
        temp = ScratchVar(TealType.bytes)
        next = ScratchVar(TealType.bytes)
        i = ScratchVar(TealType.uint64)
        _max = ScratchVar(TealType.uint64)
        return Seq(
            _max.store(self.order_index[on_addr]),
            For(i.store(Int(0)), i.load()< _max.load(), i.store(i.load() + Int(1))).Do(
                    temp.store(self.getOrderByIndex(on_addr,i.load())),
                    next.store(self.getOrderByIndex(on_addr,i.load()+Int(1))),

                    If(Len(temp.load()) == 0)
                    .Then(
                        self.setOrderOnIndex(on_addr,i.load(),next.load())
                    ),
            )
        )


    @internal(TealType.none)
    def pushOrder(self,on_addr,order):
        """Add new order to the array and update the index"""
        i = abi.make(abi.Uint8)
        # TODO: Only the administrator or the oracle can do this operation
        return Seq(
            Assert(
                Txn.sender() == self.oracle_address, # Only the oracle can do this
                self.order_index[on_addr] < Int(self.__ORDER_LIST_MAX),
            ),
            i.set(self.order_index[on_addr]),
            # self.orders[self.order_index][on_addr].set(order_id),
            self.setOrderOnIndex(on_addr,i,order),
            self.order_index[on_addr].increment(Int(1)),
        )
    @internal(TealType.bytes)
    def popOrder(self,on_addr,index):
        """remove the order id from the array"""
        # TODO: Only administrator or the oracle can do this operation
        temp = ScratchVar(TealType.bytes)
        return Seq(
            temp.store(self.getOrderByIndex(on_addr,index)),
            self.setOrderOnIndex(on_addr,index,Bytes("")),
            self.reBlockOrderList(on_addr),
            Return(temp.load())
        )

    @internal(TealType.uint64)
    def searchOrderIndex(self,on_addr,order_id: abi.String):
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
            For(i.store(Int(0)), i.load() < self.order_index[on_addr], i.store(i.load() + Int(1))).Do(
                    idx.set(i.load()),
                    (_order := self.Order()).decode(self.orders[idx][on_addr]),
                    (_order_id := abi.String()).set(_order.order_id),
                    If(_order_id.get() == order_id.get())
                    .Then(
                        r.store(i.load()+Int(1))
                    )
            ),
            # TODO: must return the index + 1, because 0 if the value is not found
            Return(r.load())
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
    def getDeposit(self,addr: abi.Account,i: abi.Uint8,*,output: Tokens):
        """Get deposit for a specific token using the index"""
        return Seq(
            output.decode(self.deposit[i][addr.address()]),
        )
    @external
    def getIncome(self,addr: abi.Account,i: abi.Uint8,*,output: Tokens):
        """Get income for a specific token using the index"""
        return Seq(
            output.decode(self.income[i][addr.address()]),
        )

    @external
    def placeOrder(self,
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
            # self.deposit.increment(product_pay.get().asset_amount()),
            output.set(Int(1))
        )

    # @external
    # def acceptOrder(self,
    #                 b: abi.Account,        # The buyer address
    #                 order_id: abi.String,  # The purchase order id
    #                 *, output: abi.String):
    #     """
    #     The seller accept the order request from the buyer,
    #     and increase the deposit on the seller account.
    #     """
    #     ###############################################################################
    #     # Due to massive order that a seller can receive, is not optimal to store all #
    #     # in the smartcontract, for the seller it will managed by the database-oracle #
    #     ###############################################################################
    #     r = abi.make(abi.Uint8)            # Return value for teh search
    #     i = abi.make(abi.Uint8)            # Real index
    #     return Seq(
    #         Assert(
    #             self.isSeller() == Int(1),
    #         ),
    #         r.set(self.searchOrderIndex(b.address(),order_id)),
    #         If(r.get() != Int(0))
    #         .Then(
    #             # Found the order, now it process to check the seller address
    #             i.set(r.get()-Int(1)),
    #             (_order := self.Order()).decode(self.orders[i][b.address()]),
    #             (seller := abi.Address()).set(_order.seller),
    #             If(seller.get() != Txn.sender())
    #             .Then(
    #                 output.set("sender_is_not_the_seller_order")
    #             )
    #             .Else(
    #                 # order snapshot
    #                 (order_id := abi.String()).set(_order.order_id),
    #                 (amount := abi.Uint64()).set(_order.amount),
    #                 (token := abi.Uint64()).set(_order.token),
    #                 (status := abi.Uint8()).set(_order.status),

    #                 Assert( status.get() == Int(self.ORDER_PENDING)),
    #                 status.set(self.ORDER_ACCEPTED),
    #                 _order.set(seller,order_id,amount,token,status),
    #                 self.orders[i][b.address()].set(_order.encode()), # update order in buyer local state.

    #                 # (_order := self.Order()).decode(self.orders[i][b.address()]),
    #                 output.set("status_order_updated")
    #             )
    #         )
    #         .Else(
    #             # The order was not found, return 0
    #             output.set("order_not_found"),
    #         ),
    #     )
    # @external
    # def rejectOrder(self,
    #                 b: abi.Account,
    #                 order_id: abi.String,
    #                 *, output: abi.String):
    #     """
    #     Seller reject the order, the smartcontract will send the tokens back.
    #     """
    #     pass

    @external
    def oPlaceOrderSuccess(self,acc:abi.Account,order: Order,i: abi.Uint8,d: Tokens,*,output:Tokens):
        """
        The oracle has processed the order, and it validated, call this function
        to lock the tokens for the bussines.
        Returns The order id.
        """
        idx = abi.make(abi.Uint8)

        return Seq(
            idx.set(self.order_index[acc.address()]),
            self.pushOrder(acc.address(),order.encode()),
            (_order := self.Order()).decode(self.orders[idx][acc.address()]),
            self.deposit[i][acc.address()].set(d.encode()),
            output.decode(self.deposit[i][acc.address()]),
            # output.decode(d),
        )


    
    # @external
    # def oOrderFail(self,
    #                b: abi.Account,
    #                amount: abi.Uint64,
    #                *, output: abi.Uint64):
    #     """If the order failed, the oracle refund the tokens to the buyer, and delere the order
    #     from the database."""
    #     return Seq(
    #         Assert(
    #             Txn.sender() == self.oracle_address, # Only the oracle can execute this action.
    #             self.deposit[b.address()] >= amount.get(), # The buyer must have funds
    #         ),
    #         self.withdrawUSDC(b.address(),amount.get()),
    #         self.deposit.decrement(amount.get()),
    #         output.set(Int(1))
    #     )
