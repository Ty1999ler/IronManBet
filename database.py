import sqlite3
import hashlib
from contextlib import contextmanager
from typing import Optional

DB_PATH = "ironman.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tournament (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                name TEXT NOT NULL,
                formula TEXT NOT NULL CHECK (formula IN ('linear', 'token')),
                total_competitors INTEGER NOT NULL,
                total_rounds INTEGER NOT NULL,
                current_round INTEGER NOT NULL DEFAULT 0,
                betting_open INTEGER NOT NULL DEFAULT 0,
                winner_id INTEGER REFERENCES competitors(id),
                organizer_password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                eliminated INTEGER NOT NULL DEFAULT 0,
                eliminated_round INTEGER
            );

            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bettor_name TEXT NOT NULL,
                competitor_id INTEGER NOT NULL REFERENCES competitors(id),
                amount REAL NOT NULL,
                round_placed INTEGER NOT NULL,
                competitors_remaining INTEGER NOT NULL,
                multiplier REAL NOT NULL,
                effective_bet REAL NOT NULL,
                placed_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)


# --- Tournament ---

def create_tournament(name: str, formula: str, competitors: list[str], password: str) -> int:
    total = len(competitors)
    import math
    total_rounds = math.ceil(math.log2(total)) if total > 1 else 1
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    with get_db() as conn:
        conn.execute("DELETE FROM bets")
        conn.execute("DELETE FROM competitors")
        conn.execute("DELETE FROM tournament")
        conn.execute(
            """INSERT INTO tournament (id, name, formula, total_competitors, total_rounds,
               current_round, betting_open, organizer_password_hash)
               VALUES (1, ?, ?, ?, ?, 0, 0, ?)""",
            (name, formula, total, total_rounds, pw_hash),
        )
        conn.executemany(
            "INSERT INTO competitors (name) VALUES (?)",
            [(c,) for c in competitors],
        )
    return total_rounds


def get_tournament() -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM tournament WHERE id = 1").fetchone()


def verify_password(password: str) -> bool:
    t = get_tournament()
    if not t:
        return False
    return t["organizer_password_hash"] == hashlib.sha256(password.encode()).hexdigest()


# --- Round management ---

def open_betting() -> bool:
    """Open betting. Sets round to 1 on first call; subsequent calls leave round unchanged."""
    t = get_tournament()
    if not t:
        return False
    with get_db() as conn:
        if t["current_round"] == 0:
            conn.execute(
                "UPDATE tournament SET current_round = 1, betting_open = 1 WHERE id = 1"
            )
        else:
            conn.execute(
                "UPDATE tournament SET betting_open = 1 WHERE id = 1"
            )
    return True


def close_betting() -> bool:
    t = get_tournament()
    if not t:
        return False
    with get_db() as conn:
        conn.execute("UPDATE tournament SET betting_open = 0 WHERE id = 1")
    return True


def eliminate_competitor(competitor_id: int) -> bool:
    t = get_tournament()
    if not t:
        return False
    with get_db() as conn:
        conn.execute(
            "UPDATE competitors SET eliminated = 1, eliminated_round = ? WHERE id = ?",
            (t["current_round"], competitor_id),
        )
        conn.execute(
            "UPDATE tournament SET current_round = current_round + 1 WHERE id = 1"
        )
    return True


def reinstate_competitor(competitor_id: int) -> bool:
    with get_db() as conn:
        conn.execute(
            "UPDATE competitors SET eliminated = 0, eliminated_round = NULL WHERE id = ?",
            (competitor_id,),
        )
    return True


def declare_winner(competitor_id: int) -> bool:
    t = get_tournament()
    if not t:
        return False
    with get_db() as conn:
        conn.execute(
            "UPDATE tournament SET winner_id = ?, betting_open = 0 WHERE id = 1",
            (competitor_id,),
        )
    return True


# --- Competitors ---

def get_competitors() -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("SELECT * FROM competitors ORDER BY name").fetchall()


def get_active_competitors() -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM competitors WHERE eliminated = 0 ORDER BY name"
        ).fetchall()


def get_competitor(competitor_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM competitors WHERE id = ?", (competitor_id,)
        ).fetchone()


# --- Multiplier calculation ---

def compute_multiplier(formula: str, competitors_remaining: int, total_rounds: int, current_round: int) -> float:
    if formula == "linear":
        rounds_remaining = total_rounds - current_round + 1
        return round(1.0 + rounds_remaining / total_rounds, 4)
    else:  # token
        return float(max(1, competitors_remaining - 1))


# --- Bets ---

def place_bet(bettor_name: str, competitor_id: int, amount: float) -> Optional[dict]:
    t = get_tournament()
    if not t or not t["betting_open"]:
        return None
    if not (1 <= amount <= 500):
        return None

    active = get_active_competitors()
    competitors_remaining = len(active)
    # Verify target competitor is active
    target_ids = {c["id"] for c in active}
    if competitor_id not in target_ids:
        return None

    multiplier = compute_multiplier(
        t["formula"], competitors_remaining, t["total_rounds"], t["current_round"]
    )
    effective_bet = round(amount * multiplier, 4)

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO bets (bettor_name, competitor_id, amount, round_placed,
               competitors_remaining, multiplier, effective_bet)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (bettor_name, competitor_id, amount, t["current_round"],
             competitors_remaining, multiplier, effective_bet),
        )
        bet_id = cur.lastrowid

    return {
        "bet_id": bet_id,
        "multiplier": multiplier,
        "effective_bet": effective_bet,
        "amount": amount,
    }


def get_all_bets() -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            """SELECT b.*, c.name as competitor_name
               FROM bets b JOIN competitors c ON b.competitor_id = c.id
               ORDER BY b.placed_at DESC"""
        ).fetchall()


def get_bets_for_competitor(competitor_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM bets WHERE competitor_id = ?", (competitor_id,)
        ).fetchall()


# --- Pool and payout calculations ---

def get_pool_stats() -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT SUM(amount) as total_pool, SUM(effective_bet) as total_effective FROM bets"
        ).fetchone()
    return {
        "total_pool": row["total_pool"] or 0.0,
        "total_effective": row["total_effective"] or 0.0,
    }


def get_competitor_odds() -> list[dict]:
    """Returns each active competitor's share of effective bets and projected payout."""
    stats = get_pool_stats()
    total_effective = stats["total_effective"]
    total_pool = stats["total_pool"]

    with get_db() as conn:
        rows = conn.execute(
            """SELECT c.id, c.name, c.eliminated,
                      COALESCE(SUM(b.effective_bet), 0) as comp_effective,
                      COALESCE(SUM(b.amount), 0) as comp_pool
               FROM competitors c
               LEFT JOIN bets b ON b.competitor_id = c.id
               GROUP BY c.id
               ORDER BY c.name"""
        ).fetchall()

    results = []
    for r in rows:
        share = (r["comp_effective"] / total_effective) if total_effective > 0 else 0.0
        projected_payout = round(share * total_pool, 2)
        results.append({
            "id": r["id"],
            "name": r["name"],
            "eliminated": bool(r["eliminated"]),
            "effective_bet": round(r["comp_effective"], 4),
            "share": round(share, 4),
            "projected_payout": projected_payout,
        })
    return results


def get_payout_breakdown(winner_id: int) -> list[dict]:
    """Final payout per bettor for the winning competitor."""
    stats = get_pool_stats()
    total_pool = stats["total_pool"]

    with get_db() as conn:
        winner_bets = conn.execute(
            "SELECT * FROM bets WHERE competitor_id = ?", (winner_id,)
        ).fetchall()

    total_winner_effective = sum(b["effective_bet"] for b in winner_bets)
    payouts = []
    for b in winner_bets:
        share = b["effective_bet"] / total_winner_effective if total_winner_effective > 0 else 0
        payout = round(share * total_pool, 2)
        payouts.append({
            "bettor_name": b["bettor_name"],
            "amount_bet": b["amount"],
            "round_placed": b["round_placed"],
            "multiplier": b["multiplier"],
            "effective_bet": b["effective_bet"],
            "share": round(share, 4),
            "payout": payout,
        })
    payouts.sort(key=lambda x: x["payout"], reverse=True)
    return payouts
