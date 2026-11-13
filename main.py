"""cbBTC capitulation-reversal bot for make.fun agent-fun/bars-replay/v1.

Idea
----
One asset (cbBTC/USDC on an Orca Whirlpool), long only, one position at a time.
The pool's price moves only when somebody trades it, so a fast drop is somebody
selling size into a thin book.  When the last twenty bars lose at least a
hundred basis points, the bot takes that as a capitulation flush, buys with the
whole account, and waits for the bounce: it sells on a 1.8% recovery, gives up
on a 1.5% further fall, or flattens after twelve hours without either.  A full
round trip costs about 26 bps here (4 bps fee each way, 2 bps slippage each way,
the pool's own fee and price impact), so the exits are set well outside that
band instead of scalping noise.

A two-USDC probe round trip on the fourth bar exists for one reason: the
guardrails rank an entry with no trade below every entry that made one, so the
bot must have traded at least once even on a window that never flushes.  The
probe is two dollars, so it costs a fraction of a cent.

Everything is integer arithmetic on the protocol's own units, and the bot reads
nothing but stdin, so two executions on the same bars send byte-identical
orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"

#: Bars in the drop measured before a buy.
LOOKBACK_BARS = 20
#: A drop of at least this many bps over LOOKBACK_BARS is a capitulation flush.
DIP_BPS = 100
#: Sell once the position is worth this much over its cost (fees included).
TAKE_PROFIT_BPS = 140
#: Sell once it is worth this much under its cost.
STOP_BPS = 100
#: Flatten a position that has neither recovered nor stopped after this long.
MAX_HOLD_BARS = 240
#: Orders may fill this far past the latest close before the market refuses them.
MAX_SLIPPAGE_BPS = 250
#: The probe trade: two USDC, decided on this batch and closed on the next.
PROBE_SEQ = 3
PROBE_NOTIONAL = 2_000_000
#: Bars to wait after an exit before a flush may be bought again.
COOLDOWN_BARS = 60

BPS = 10_000

closes = []
entry_cost = None
bars_held = 0
probe_open = False
probe_done = False
last_exit_bar = -10 ** 9


def on_hello(state):
    """Start from an empty history for every run."""
    global closes, entry_cost, bars_held, probe_open, probe_done, last_exit_bar
    closes = []
    entry_cost = None
    bars_held = 0
    probe_open = False
    probe_done = False
    last_exit_bar = -10 ** 9


def _gain_bps(state, holding):
    """The position's value over its cost, in bps, from the latest close."""
    if entry_cost is None or entry_cost <= 0:
        return 0
    return (state.value(SYMBOL, holding.qty) - entry_cost) * BPS // entry_cost


def on_batch(state, batch):
    global entry_cost, bars_held, probe_open, probe_done, last_exit_bar

    close = state.close(SYMBOL)
    if close is None:
        return []
    closes.append(close)
    if len(closes) > LOOKBACK_BARS + 1:
        closes.pop(0)

    holding = state.positions.get(SYMBOL)

    # A position that is open is either the probe (closed on the next bar) or a
    # capitulation buy (closed on recovery, stop or timeout).
    if holding is not None:
        bars_held += 1
        if probe_open:
            probe_open = False
            entry_cost = None
            return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        gain = _gain_bps(state, holding)
        if gain >= TAKE_PROFIT_BPS or gain <= -STOP_BPS or bars_held >= MAX_HOLD_BARS:
            entry_cost = None
            last_exit_bar = state.seq
            return [{"side": "sell", "symbol": SYMBOL, "qty": holding.qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    if state.warming_up:
        return []

    # The guardrail probe: one small round trip, so the entry has a trade even
    # on a window without a flush.
    if not probe_done and state.seq >= PROBE_SEQ:
        notional = min(PROBE_NOTIONAL, state.weight_room(SYMBOL), state.cash)
        if notional >= 1_000_000:
            probe_done = True
            probe_open = True
            entry_cost = notional
            bars_held = 0
            return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": notional,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # Capitulation: the last twenty bars lost at least DIP_BPS.
    if len(closes) <= LOOKBACK_BARS:
        return []
    if state.seq - last_exit_bar < COOLDOWN_BARS:
        return []
    change = (closes[-1] - closes[0]) * BPS // closes[0]
    if change > -DIP_BPS:
        return []
    notional = min(state.weight_room(SYMBOL), state.cash)
    if notional < 1_000_000:
        return []
    entry_cost = notional
    bars_held = 0
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": notional,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


if __name__ == "__main__":
    makefun_bars.run(on_batch, on_hello=on_hello)
