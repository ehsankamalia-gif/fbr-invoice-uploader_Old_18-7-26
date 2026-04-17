## Advance Booking: Model Counter + Two-Stage Payment

### Model-Level Booking Counter

Each motorcycle model maintains its own independent sequential counter.

- A counter row is stored in `advance_booking_model_counters`.
- Key: `model_code` (uppercase alphanumeric, derived from `motorcycle_model`; e.g. `CD 70` → `CD70`).
- On every new booking for that model:
  - The system locks the counter row (transactional row lock where supported).
  - Increments `last_seq` by `1`.
  - Stores the incremented value as `AdvanceBooking.model_seq`.
  - Generates `AdvanceBooking.booking_number` as `{MODEL_CODE}-{SEQ}` (e.g. `CD70-1`, `CD70-2`).

This guarantees:
- Sequential numbering starting at `1` per model
- No duplicates
- No gaps when the transaction fails (counter increment rolls back with the booking)

### Two-Stage Payment Workflow

#### Stage 1: Booking (Partial Payment)

When a booking is created:
- `total_price` is set from the Price table (Model + Color)
- `advance_paid` is collected at booking time
- `balance_amount = total_price - advance_paid` (remaining amount due)

An audit entry is written:
- `advance_booking_audit.action = BOOKING_PAYMENT`

A ledger entry is written (cash received):
- `spare_ledger_transactions.trans_type = CREDIT`
- `amount = advance_paid`
- `reference_number = booking_number`

#### Stage 2: Delivery (Balance Payment Required)

When delivery is confirmed:
- The system requires `delivery_paid` to match the current `balance_amount` exactly.
- If the balance is not paid in full, delivery is blocked.

On successful delivery:
- `balance_amount` becomes `0`
- `delivery_paid` is stored on the booking
- A ledger entry is written (cash received):
  - `spare_ledger_transactions.trans_type = CREDIT`
  - `amount = delivery_paid`

Audit entries are written:
- `DELIVERY_PAYMENT` (records before/after balance)
- `APPLY_ON_DELIVERY` (applies any outstanding advance bookkeeping fields)

#### Return / Delivery Reversal

If a delivery is reversed (Mark Active):
- `balance_amount` is restored to `total_price - advance_paid`
- `delivery_paid` is reset to `0`
- A ledger reversal entry is written:
  - `spare_ledger_transactions.trans_type = DEBIT`
  - `amount = previously recorded delivery_paid`
- Audit entries are written:
  - `REVERSE_DELIVERY`
  - `REVERSE_DELIVERY_PAYMENT`

