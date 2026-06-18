# Ironman Betting — Rules

A pool betting game for an elimination-style tournament. **There is no house cut — 100% of the pool goes to the winner's backers.**

## The basics

| Setting | Value |
|---|---|
| Minimum bet | $1 |
| Maximum bet | $500 per bet |
| Bets per person | Unlimited — bet on multiple people, multiple times |
| Can competitors bet? | Yes, including on themselves |
| Betting windows | The organizer opens and closes betting each round |
| Pool cut | None |

## How payouts work

Everyone's money goes into one pool. When a competitor wins, **the people who bet on that competitor split the entire pool** — divided in proportion to their *effective bet*.

```
effective_bet = amount × multiplier
your_payout   = (your effective bet on the winner ÷ total effective bets on the winner) × total pool
```

If you're the only one who backed the winner, you take the whole pool. If several people backed them, you split it by effective bet.

## The multiplier (why timing matters)

Your bet is weighted by *when* you place it. Earlier bets earn a higher multiplier, because you're committing with less information. The organizer picks one of two formulas at setup (locked once the first bet is placed).

For an **N-competitor** game, one player is eliminated per round, so `total_rounds = N − 1`.

### Formula A — Linear Decay (gentle)

```
multiplier = 2 − (current_round − 1) / (total_rounds − 1)
```

Runs from **2.0×** in round 1 down to exactly **1.0×** in the final round, regardless of how many players there are.

### Formula B — Token (steep)

```
multiplier = competitors_remaining − 1
```

Starts at **(N − 1)×** in round 1 and falls to **1×** at the final two. Rewards early commitment much more aggressively, and gets steeper with more players.

### Example — 8 players (`total_rounds = 7`)

| Round | Players left | Linear | Token |
|------:|-------------:|-------:|------:|
| 1 | 8 | 2.000× | 7× |
| 2 | 7 | 1.833× | 6× |
| 3 | 6 | 1.667× | 5× |
| 4 | 5 | 1.500× | 4× |
| 5 | 4 | 1.333× | 3× |
| 6 | 3 | 1.167× | 2× |
| 7 | 2 | 1.000× | 1× |

A **$20 bet in round 1** is worth `$40` effective under Linear, or `$140` under Token. A **$20 bet in the final round is worth exactly `$20`** under either formula — no bonus once you have full information.

## "Odds" on the tracker

The tracker's implied odds aren't a separate formula — they just reflect where the money currently sits:

```
share  = a competitor's effective bets ÷ all effective bets
return = 1 / share
```

That's the crowd's current opinion. The actual payout always uses the equation above: the winner's backers split the whole pool by effective bet.
