# Critical Fix: Handler Dependencies

## Problem
The bot was crashing with `NameError: name 'db' is not defined` in `handlers/orders.py`.
This was happening because several handlers were trying to access `db` (and `bot`) as global variables or closure variables, but they were not available in the scope.
The dependency injection middleware expects these dependencies to be declared as arguments in the handler function.

## Solution
Updated the signatures of the following handlers in `handlers/orders.py` to accept `db: DatabaseProtocol` and `bot: Any` (where needed):

1.  `order_payment_proof_invalid`
2.  `order_payment_proof`
3.  `confirm_payment`
4.  `reject_payment`
5.  `confirm_order`
6.  `cancel_order`
7.  `cancel_order_customer`

## Verification
-   The `NameError` should be resolved.
-   Order processing flows (payment proof, confirmation, cancellation) should now work correctly.
