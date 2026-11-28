# Golden fixture B: the arithmetic

One AE team (`AE-SMB`), two source lanes (`Paid`, `Outbound`), six months
(2025-02 to 2025-07, called m1 to m6). Inputs are in `inputs.yaml`, the answer
in `expected.yaml`. `tests/test_workload_fixture.py` loads the answer into a
`Snapshot`, checks the identities, and reruns these rules in a separate
reference simulation.

## Rules

- **Capacity.** Ceiling 4 open deals per ramped AE. An AE counts 0 in the start
  month and 1 from the next month. Two AEs are ramped throughout. The third was
  planned for April (ramped from May) and started in June (ramped from July):
  ramped heads `2 2 2 2 2 3`, capacity `8 8 8 8 8 12`. Had the hire not slipped,
  capacity would be `8 8 8 12 12 12`.
- **Room** in a month = capacity - open_start + wins + losses (slots released by
  closings are usable in the same month). Admissions never exceed room.
- **Routing (design default).** Oldest demand first: retried demand
  (`queue_start`) before new demand. Within an age class, room splits across
  lanes in proportion to class size; for new demand the size is arrivals minus
  `rejected_fit`, so the split is proportional to arrivals.
- **Fractions.** Largest remainder: each lane takes the floor of its exact
  share, leftover slots go one each to the largest fractional parts, ties to
  the earlier lane (Paid before Outbound).
- **Queue.** Demand not admitted in its arrival month waits one month. If it is
  still not admitted it expires at that month's end (`expired_no_capacity`).
  `rejected_fit` leaves from new arrivals before admission.
- **Lifetime.** A deal admitted in month m closes in month m+2. The 6 deals
  open at the start close on the `initial_closings` schedule.
- **Outcomes.** Cumulative wins = floor(rate x cumulative closings + 1/2); the
  month's wins are the increase. Paid rate 1/2, Outbound 1/3.
- **Bookings** = wins x deal size (Paid 1,000,000 cents, Outbound 2,000,000).

## Month by month

Open at start: Paid 4, Outbound 2 (6 of 8 slots).

**m1.** Closings: Paid 1, Out 1. Room = 8 - 6 + 2 = 4. No retry demand. New:
Paid 4, Out 2 (6 > 4). Shares 4x4/6 = 2.67, 4x2/6 = 1.33. Floors 2 and 1, one
slot left, largest fraction is Paid's .67: Paid 3, Out 1. Queue end: Paid 1,
Out 1. Wins: Paid floor(.5 + .5) = 1; Out floor(1/3 + .5) = 0, so Out's closing
is a loss. Open end: Paid 4 + 3 - 1 = 6; Out 2 + 1 - 1 = 2.

**m2.** Closings: Paid 2, Out 0. Room = 8 - 8 + 2 = 2. Retry: Paid 1, Out 1 (2 =
room), both admitted; nothing left for new. New: Paid 3 - 1 rejected = 2, Out 3,
all queue. Cumulative Paid closings 3: floor(1.5 + .5) = 2, minus 1 before = 1
win, 1 loss. Open end: Paid 6 + 1 - 2 = 5; Out 2 + 1 - 0 = 3.

**m3.** Closings: Paid 1 initial + 3 admitted in m1 = 4; Out 1 + 1 = 2. Room =
8 - 8 + 6 = 6. Retry: Paid 2, Out 3 (5 <= 6), all admitted; 1 slot left. New:
Paid 4, Out 2: shares 0.67 and 0.33, floors 0 and 0, the slot goes to Paid.
Admissions Paid 3, Out 3. Wins: Paid cumulative closings 7, floor(3.5 + .5) = 4,
minus 2 = 2 wins, 2 losses; Out cumulative 3, floor(1 + .5) = 1, minus 0 = 1
win, 1 loss. Open end: Paid 5 + 3 - 4 = 4; Out 3 + 3 - 2 = 4.

**m4.** Closings: Paid 1 (admitted m2), Out 1. Room = 8 - 8 + 2 = 2. Retry:
Paid 3, Out 2 (5 > 2). Shares 2x3/5 = 1.2, 2x2/5 = 0.8: floors 1 and 0, the slot
goes to Out (.8): Paid 1, Out 1. Unadmitted retry expires: Paid 2, Out 1
(`expired_no_capacity`). New: Paid 3, Out 2 - 1 rejected = 1, no room, queue.
Wins: Paid cumulative 8, floor(4 + .5) = 4, no increase: 0 wins, 1 loss. Out
cumulative 4, floor(4/3 + .5) = 1, no increase: 0 wins, 1 loss. Open end: Paid
4 + 1 - 1 = 4; Out 4 + 1 - 1 = 4.

**m5.** Closings: Paid 3 (admitted m3), Out 3. Room = 8 - 8 + 6 = 6 (the hire
started this month and is not yet ramped). Retry: Paid 3, Out 1 (4), all
admitted; 2 left. New: Paid 3, Out 3, 1 slot each. Admissions Paid 4, Out 2.
Wins: Paid cumulative 11, floor(5.5 + .5) = 6, minus 4 = 2 wins, 1 loss. Out
cumulative 7, floor(7/3 + .5) = 2, minus 1 = 1 win, 2 losses. Open end: Paid
4 + 4 - 3 = 5; Out 4 + 2 - 3 = 3.

**m6.** Capacity 12. Closings: Paid 1 (admitted m4), Out 1. Room = 12 - 8 + 2 =
6. Retry: Paid 2, Out 2 (4), all admitted; 2 left. New: Paid 4, Out 2: shares
1.33 and 0.67, floors 1 and 0, the slot goes to Out (.67): Paid 1, Out 1.
Admissions Paid 3, Out 3. Wins: Paid cumulative 12, floor(6 + .5) = 6, no
increase: 0 wins, 1 loss. Out cumulative 8, floor(8/3 + .5) = 3, minus 2 = 1 win,
0 losses. Open end: Paid 5 + 3 - 1 = 7; Out 3 + 3 - 1 = 5 (12 = capacity).

## Checks

Team room by month `4 2 6 2 6 6` equals team admissions (`3+1, 1+1, 3+3, 1+1,
4+2, 3+3`): the team is full every month, so the capacity inequality holds with
equality. The slipped hire withholds 4 slots in each of m4 and m5 (capacity 8
instead of 12), which is why m4 admits 2 and expires 3 retried leads.
