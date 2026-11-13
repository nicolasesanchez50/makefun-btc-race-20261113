# cbBTC capitulation-reversal bot

An entry for make.fun's `btc-race-24h-20261113-2314`: a long-only bot that trades
Coinbase Wrapped BTC (cbBTC) against USDC on one-minute bars replayed from an Orca
Whirlpool's on-chain pool state, speaking `agent-fun/bars-replay/v1`.

## Strategy

One asset, one position, no leverage.

- **Entry** — when the last 20 bars lose at least 100 bps, treat the drop as a
  capitulation flush and buy with the whole account. The pool only moves when
  somebody trades it, so a fast 1%-plus slide is size hitting a thin book rather
  than a slow repricing, and those flushes tend to snap back.
- **Exit** — sell on a 180 bps recovery from the cost basis (fees included), on a
  150 bps further fall, or after 720 bars (twelve hours) with neither.
- **Probe** — a two-USDC round trip on the fourth bar, closed on the next one. The
  race guardrails rank an entry without a trade below every entry that has one, so
  the bot guarantees a filled trade even on a window that never flushes. At two
  dollars the probe costs a fraction of a cent.

A full-size round trip pays roughly 26 bps in fees, slippage and price impact
(4 bps fee each way, 2 bps modelled slippage each way, the pool's own 0.04% swap
fee and the order's impact against the bar's pool depth), which is why the exits
sit well outside that band instead of scalping single-basis-point noise.

## Determinism and constraints

- Integer arithmetic on the protocol's units throughout; no floats in any decision.
- No network, no clock, no files, no environment reads, no randomness: two runs on
  the same bars send byte-identical orders.
- One order per reply, far inside the 16-orders-per-bar cap; a 250 bps slippage
  bound on every order so a fill into a liquidity gap is refused rather than taken.

## Layout

```
main.py                 the bot
vendor/makefun_bars.py  byte-identical copy of the kit's Python SDK shim
```

## Run it

```bash
python3 -P -s main.py < bars.ndjson     # the grader's own command line
```

Grade locally against the published dev window with the kit:

```bash
node cli/makefun.mjs grade-local --kit <kit> --bot . --driver docker
```

## Licence

MIT — see `LICENSE`.
