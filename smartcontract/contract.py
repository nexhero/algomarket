from pyteal import *
from pyteal import Subroutine
CONST_USDC_ID = 98_430_563        # TODO: Change to the real usdc asset id

# Default values.
CONST_COMMISSION_FEES = 1
CONST_ORACLE_FEES = 50000
CONST_PREMIUM_COST = 100000

def approval_program():
    ####################################
    # DEFINE GLOBAL A LOCAL VARIABLES  #
    ####################################
    # Global Variables.
    earning = Bytes("earning")               # int - acumulate revenue for commission
    commission_fees = Bytes("commission_fees") # int - % charged to the seller for selling products
    oracle_fees = Bytes("oracle_fees")          # int - The cost per transaction for using the oracle
    premium_cost = Bytes("premium_cost")     # int - Price in microAlgos for becoming a premium seller.
    admin = Bytes("admin_addr")              # bytes slices - Administrator address,
    oracle = Bytes("oracle_addr")            # bytes slices - Oracle address
    #Local Variables
    deposit = Bytes("deposit")  # int - usdc deposited by the seller and not processed by oracle nor smart contract.
    income = Bytes("gains")     # int - incoming usdc for selling products, ready to withdraw.
    premium = Bytes("premium")  # int - Flag variable to manage if the seller is a premium member.

    ##########################
    # DEFINE UTILS FUNCTIONS #
    ##########################

    @Subroutine(TealType.uint64)
    def isAddrAdmin(addr):
        return If(addr == App.globalGet(admin)).Then(Return(Int(1))).Else(Return(Int(0)))

    @Subroutine(TealType.uint64)
    def isAddrOracle(addr):
        return If(addr == App.globalGet(oracle)).Then(Return(Int(1))).Else(Return(Int(0)))

    @Subroutine(TealType.uint64)
    def isPremium(addr):
        return App.localGet(addr,premium)

    @Subroutine(TealType.none)
    def setPremium(addr):
        _premium_price = ScratchVar(TealType.uint64)
        return Seq(
            _premium_price.store(App.globalGet(premium_cost)),
            Assert(
                And(
                    isPremium(addr) == Int(0),
                    Global.group_size() == Int(2),
                    Gtxn[1].type_enum() == TxnType.Payment,
                    Gtxn[1].amount() >= _premium_price.load(),
                )
            ),
            App.localPut(addr,premium,Int(1)),
            Approve()
        )

    @Subroutine(TealType.none)
    def usdcWithdraw(addr,amount):
        return Seq([
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: Int(CONST_USDC_ID),
                    TxnField.asset_amount: amount,
                    TxnField.asset_receiver: addr,
                }
            ),
            InnerTxnBuilder.Submit(),
        ])

    @Subroutine(TealType.uint64)
    def getDeposit(addr):
        return Seq(
            Return(App.localGet(addr,deposit))
        )
    @Subroutine(TealType.uint64)
    def getIncome(addr):
        return Return(App.localGet(addr,income))

    @Subroutine(TealType.uint64)
    def getTokenBalance():
        balance = AssetHolding.balance(Global.current_application_address(),Int(CONST_USDC_ID))
        return Seq(
            balance,
            Return(balance.value())
        )

    # Return 1 is the function completed on success otherwise return 0
    @Subroutine(TealType.uint64)
    def sellerWithdraw(account,amount):
        return Seq([
            If(getIncome(account) >= amount)
            .Then(
                usdcWithdraw(account,amount),
                App.localPut(account,income,getIncome(account) - amount),
                Return(Int(1))
            ).Else(
                Return(Int(0))
            )
        ])

    @Subroutine(TealType.uint64)
    def buyerWithdraw(account,amount):
        return Seq([
            If(getDeposit(account) >= amount)
            .Then(
                usdcWithdraw(account,amount),
                App.localPut(account,deposit,getDeposit(account) - amount),
                Return(Int(1))
            ).Else(
                Return(Int(0))
            )
        ])

    @Subroutine(TealType.uint64)
    def calcCommission(amount,is_premium):
        r = ScratchVar(TealType.uint64)
        return Seq([
            r.store(amount / Int(100)),
            If(is_premium == Int(0))
            .Then(Return(r.load()))
            .Else(Return((r.load() / Int(100)) * Int(75))) # get the 75% out of 1% of the total amount.
        ])

    # Move funds from the buyer to the seller
    @Subroutine(TealType.none)
    def moveFundsBuyerSeller(_buyer,_seller,amount):
        b_deposit = ScratchVar(TealType.uint64)
        s_income = ScratchVar(TealType.uint64)
        _earning = ScratchVar(TealType.uint64)
        _commission = ScratchVar(TealType.uint64)
        return Seq([
            b_deposit.store(getDeposit(_buyer)),
            s_income.store(getIncome(_seller)),
            _earning.store(App.globalGet(earning)),
            _commission.store(calcCommission(amount, isPremium(_seller))),
            # Check for deposit available
            Assert(b_deposit.load()>=amount),
            # Calculate the commision and move the funds from buyer to the seller and add the commision to the smart contract.
            App.localPut(_buyer,deposit,b_deposit.load() - amount),
            App.localPut(_seller,income,s_income.load() + (amount - _commission.load())),
            App.globalPut(earning,_earning.load() + _commission.load())
        ])

    # TODO: Make this action more versatil
    @Subroutine(TealType.none)
    def setup():
        return Seq([
            # Check if is admin making the request
            Assert(isAddrAdmin(Txn.sender())),
            # Opt in usdc asset
            InnerTxnBuilder.Begin(),
            InnerTxnBuilder.SetFields(
                {
                    TxnField.type_enum: TxnType.AssetTransfer,
                    TxnField.xfer_asset: Int(CONST_USDC_ID),
                    TxnField.asset_receiver: Global.current_application_address(),
                }
            ),
            InnerTxnBuilder.Submit(),
            Approve()
        ])

    #################################
    # Define actions for the actors #
    #################################
    # The buyer pay commission for post orders, all the orders will be encrypted
    # in the note section of the transaction.
    @Subroutine(TealType.none)
    def postOrder():
        account = ScratchVar(TealType.bytes)
        amount = ScratchVar(TealType.uint64)
        return Seq([
            account.store(Txn.sender()),
            Assert(
                And(
                    Global.group_size() == Int(3),
                    # Validate USDC asset
                    Gtxn[1].type_enum() == TxnType.AssetTransfer,
                    Gtxn[1].asset_receiver() == Global.current_application_address(),
                    Gtxn[1].xfer_asset() == Int(CONST_USDC_ID),
                    # Validate Payment for the Oracle
                    Gtxn[2].type_enum() == TxnType.Payment,
                    Gtxn[2].amount() == App.globalGet(oracle_fees),
                    Gtxn[2].receiver() == App.globalGet(oracle),
                )
            ),

            amount.store(Gtxn[1].asset_amount()),
            App.localPut(account.load(),deposit,getDeposit(account.load()) + amount.load())

        ])

    # The buyer make a request to cancel a specific order
    # This function only check for the buyer paying the fees for using the oracle,
    # if all is correct, then the oracle will check validate the request, and transfer usdc to the buyer address
    @Subroutine(TealType.none)
    def cancelOrder():
        return Seq([
            Assert(
                And(
                    Global.group_size() == Int(2),
                    Gtxn[1].type_enum() == TxnType.Payment,
                    Gtxn[1].receiver() == App.globalGet(oracle),
                    Gtxn[1].amount() >= App.globalGet(oracle_fees),
                    getDeposit(Txn.sender()) >= Int(0), # It can't request for cancel order if the buyer already accepted the order.
                )
            )
        ])

    #############################################
    # The seller accept the order from the user #
    #############################################
    # TODO: for the moment only accept one order per request, find a solution to request multiple orders
    @Subroutine(TealType.none)
    def acceptOrder():
        return Seq([
            Assert(
                And(
                    Global.group_size() == Int(2),
                    Gtxn[1].type_enum() == TxnType.Payment,
                    Gtxn[1].receiver() == App.globalGet(oracle),
                    Gtxn[1].amount() >= App.globalGet(oracle_fees),
                )
            )
        ])

    # The seller reject order
    # TODO: For the moment only can cancel one order per transaction
    @Subroutine(TealType.none)
    def rejectOrder():
        return Seq([
            Assert(
                And(
                    Global.group_size() == Int(2),
                    Gtxn[1].type_enum() == TxnType.Payment,
                    Gtxn[1].receiver() == App.globalGet(oracle),
                    Gtxn[1].amount() >= App.globalGet(oracle_fees),
                )
            )
        ])

    ##########################################
    # Define actions for the oracle or admin #
    ##########################################

    # Callback when the order has been canceled by buyer, declined by seller or rejected when the
    # oracle can't validate it.
    #
    # args[0] - oracle_cancel_order
    # args[1] - amount to remove
    # accounts[1] - the buyer address who request the cancelation.
    @Subroutine(TealType.none)
    def oCancelOrder():
        sender = ScratchVar(TealType.bytes)
        _buyer = ScratchVar(TealType.bytes)
        amount = ScratchVar(TealType.uint64)
        return Seq([
            sender.store(Txn.sender()),
            _buyer.store(Txn.accounts[1]),
            amount.store(Btoi(Txn.application_args[1])),

            Assert(
                And(
                    Or(isAddrOracle(sender.load()),isAddrAdmin(sender.load())), # check if the sender is a valid address.
                    getDeposit(_buyer.load()) >= amount.load(), # user has enough usdc deposited.
                )
            ),
            # If everthing is correct, send usdc to the user
            usdcWithdraw(_buyer.load(),amount.load()),
        ])

    # The seller take the order, the oracle move funds from buyer to the seller
    # args[0] - oracle_take_order
    # args[1] - amount
    # accounts[1] - seller address
    # accounts[2] - buyer address
    @Subroutine(TealType.none)
    def oTakeOrder():
        sender = ScratchVar(TealType.bytes)
        _seller = ScratchVar(TealType.bytes)
        _buyer = ScratchVar(TealType.bytes)
        amount = ScratchVar(TealType.uint64)
        return Seq([
            sender.store(Txn.sender()),
            _seller.store(Txn.accounts[1]),
            _buyer.store(Txn.accounts[2]),
            amount.store(Btoi(Txn.application_args[1])),
            Assert(
                And(
                    Or(isAddrOracle(sender.load()), isAddrAdmin(sender.load())),
                )
            ),
            moveFundsBuyerSeller(_buyer.load(),_seller.load(),amount.load()),
        ])


    handle_creation = Seq([
        # Set initial default values.
        App.globalPut(admin,Txn.sender()), # Set the administrador addr.
        App.globalPut(oracle,Txn.sender()),
        App.globalPut(earning,Int(0)),
        App.globalPut(commission_fees,Int(CONST_COMMISSION_FEES)),
        App.globalPut(oracle_fees,Int(CONST_ORACLE_FEES)),
        App.globalPut(premium_cost,Int(CONST_PREMIUM_COST)),
        Return(Int(1))
    ])
    handle_noop = Seq(
        [Cond(
            [Txn.application_args[0] == Bytes("setup"), setup()],
            [Txn.application_args[0] == Bytes("set_premium"),setPremium(Txn.sender())],
            [Txn.application_args[0] == Bytes("post_order_request"),postOrder()],
            [Txn.application_args[0] == Bytes("cancel_order_request"),cancelOrder()],
            [Txn.application_args[0] == Bytes("accept_order_request"),acceptOrder()],
            [Txn.application_args[0] == Bytes("reject_order_request"),rejectOrder()],
            [Txn.application_args[0] == Bytes("oracle_cancel_order"),oCancelOrder()],
            [Txn.application_args[0] == Bytes("oracle_take_order"),oTakeOrder()],
        ),
         Approve()
    ])

    handle_optin = Seq([
        # Set default values for the users.
        App.localPut(Int(0),deposit,Int(0)),
        App.localPut(Int(0),income,Int(0)),
        App.localPut(Int(0),premium,Int(0)),
        Return(Int(1))
    ])

    handle_closeout = Seq([
        Return(Int(1))
    ])

    handle_updateapp = Approve() # TODO: Err()  when smart contract is ready.

    handle_deleteapp = Err()

    program = Cond(
        [Txn.application_id() == Int(0), handle_creation],
        [Txn.on_completion() == OnComplete.NoOp, handle_noop],
        [Txn.on_completion() == OnComplete.OptIn, handle_optin],
        [Txn.on_completion() == OnComplete.CloseOut, handle_closeout],
        [Txn.on_completion() == OnComplete.UpdateApplication, handle_updateapp],
        [Txn.on_completion() == OnComplete.DeleteApplication, handle_deleteapp]
    )
    return program

def clear_state_program():
    program = Return(Int(1))
    return program
