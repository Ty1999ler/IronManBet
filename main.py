from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import database as db

app = FastAPI(title="Ironman Betting")
db.init_db()

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/bet.html")


@app.get("/organizer")
def organizer_page():
    return FileResponse("static/organizer.html")


@app.get("/tracker")
def tracker_page():
    return FileResponse("static/tracker.html")


@app.get("/rules")
def rules_page():
    return FileResponse("static/rules.html")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TournamentSetup(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    formula: str
    competitors: list[str]
    password: str = Field(..., min_length=1)

    @field_validator("formula")
    @classmethod
    def formula_valid(cls, v):
        if v not in ("linear", "token"):
            raise ValueError("formula must be 'linear' or 'token'")
        return v

    @field_validator("competitors")
    @classmethod
    def competitors_valid(cls, v):
        if len(v) < 2:
            raise ValueError("Need at least 2 competitors")
        if len(v) > 64:
            raise ValueError("Maximum 64 competitors")
        cleaned = [c.strip() for c in v if c.strip()]
        if len(cleaned) != len(v):
            raise ValueError("Competitor names cannot be blank")
        if len(set(c.lower() for c in cleaned)) != len(cleaned):
            raise ValueError("Competitor names must be unique")
        return cleaned


class OrganizerAuth(BaseModel):
    password: str


class EliminateRequest(BaseModel):
    password: str
    competitor_id: int


class DeclareWinnerRequest(BaseModel):
    password: str
    competitor_id: int


class SaveRequest(BaseModel):
    password: str
    name: str = Field(..., min_length=1, max_length=60)
    passphrase: str = Field(..., min_length=1)


class SaveActionRequest(BaseModel):
    password: str
    name: str
    passphrase: str


class BetRequest(BaseModel):
    bettor_name: str = Field(..., min_length=1, max_length=100)
    competitor_id: int
    amount: float = Field(..., ge=1, le=500)

    @field_validator("bettor_name")
    @classmethod
    def strip_name(cls, v):
        return v.strip()


# ---------------------------------------------------------------------------
# Organizer routes
# ---------------------------------------------------------------------------

@app.post("/api/organizer/setup")
def setup_tournament(body: TournamentSetup):
    total_rounds = db.create_tournament(
        body.name, body.formula, body.competitors, body.password
    )
    return {"ok": True, "total_rounds": total_rounds}


@app.post("/api/organizer/open-betting")
def open_betting(body: OrganizerAuth):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    t = db.get_tournament()
    if not t:
        raise HTTPException(status_code=400, detail="No tournament set up")
    if t["betting_open"]:
        raise HTTPException(status_code=400, detail="Betting is already open")
    if t["winner_id"]:
        raise HTTPException(status_code=400, detail="Tournament is over")
    db.open_betting()
    return {"ok": True}


@app.post("/api/organizer/close-betting")
def close_betting(body: OrganizerAuth):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    t = db.get_tournament()
    if not t:
        raise HTTPException(status_code=400, detail="No tournament set up")
    if not t["betting_open"]:
        raise HTTPException(status_code=400, detail="Betting is already closed")
    db.close_betting()
    return {"ok": True}


@app.post("/api/organizer/eliminate")
def eliminate(body: EliminateRequest):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    t = db.get_tournament()
    if not t:
        raise HTTPException(status_code=400, detail="No tournament set up")
    if t["betting_open"]:
        raise HTTPException(status_code=400, detail="Close betting before eliminating")
    competitor = db.get_competitor(body.competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if competitor["eliminated"]:
        raise HTTPException(status_code=400, detail="Already eliminated")
    db.eliminate_competitor(body.competitor_id)
    return {"ok": True}


@app.post("/api/organizer/testmode")
def testmode():
    """Build a fully-simulated 20-player demo tournament at the final 4.
    Organizer password for the seeded tournament is 'TestMode'."""
    db.seed_test_mode()
    return {"ok": True, "password": "TestMode"}


@app.post("/api/organizer/reinstate")
def reinstate(body: EliminateRequest):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    competitor = db.get_competitor(body.competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if not competitor["eliminated"]:
        raise HTTPException(status_code=400, detail="Competitor is not eliminated")
    db.reinstate_competitor(body.competitor_id)
    return {"ok": True}


@app.post("/api/organizer/declare-winner")
def declare_winner(body: DeclareWinnerRequest):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    t = db.get_tournament()
    if not t:
        raise HTTPException(status_code=400, detail="No tournament set up")
    competitor = db.get_competitor(body.competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if competitor["eliminated"]:
        raise HTTPException(status_code=400, detail="Eliminated competitor cannot win")
    db.declare_winner(body.competitor_id)
    payouts = db.get_payout_breakdown(body.competitor_id)
    pool = db.get_pool_stats()
    return {
        "ok": True,
        "winner": competitor["name"],
        "total_pool": pool["total_pool"],
        "payouts": payouts,
    }


@app.get("/api/organizer/bets")
def get_all_bets(password: str):
    if not db.verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid password")
    bets = db.get_all_bets()
    return [dict(b) for b in bets]


@app.post("/api/organizer/save")
def save_state(body: SaveRequest):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    res = db.save_snapshot(body.name, body.passphrase)
    if not res["ok"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return {"ok": True}


@app.get("/api/organizer/saves")
def list_saves(password: str):
    if not db.verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid password")
    return db.list_saves()


@app.post("/api/organizer/restore")
def restore_state(body: SaveActionRequest):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    res = db.restore_snapshot(body.name, body.passphrase)
    if not res["ok"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return {"ok": True}


@app.post("/api/organizer/delete-save")
def delete_save(body: SaveActionRequest):
    if not db.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    res = db.delete_save(body.name, body.passphrase)
    if not res["ok"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return {"ok": True}


@app.get("/api/organizer/status")
def organizer_status(password: str):
    if not db.verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid password")
    t = db.get_tournament()
    if not t:
        raise HTTPException(status_code=404, detail="No tournament set up")
    competitors = db.get_competitors()
    pool = db.get_pool_stats()
    odds = db.get_competitor_odds()

    winner = None
    if t["winner_id"]:
        w = db.get_competitor(t["winner_id"])
        winner = {"id": w["id"], "name": w["name"]}
        payouts = db.get_payout_breakdown(t["winner_id"])
    else:
        payouts = []

    return {
        "tournament": dict(t),
        "competitors": [dict(c) for c in competitors],
        "pool": pool,
        "odds": odds,
        "winner": winner,
        "payouts": payouts,
    }


# ---------------------------------------------------------------------------
# Public / Tracker routes
# ---------------------------------------------------------------------------

@app.get("/api/status")
def public_status():
    t = db.get_tournament()
    if not t:
        return {"tournament": None}

    active = db.get_active_competitors()
    all_competitors = db.get_competitors()
    pool = db.get_pool_stats()
    odds = db.get_competitor_odds()

    current_multiplier = None
    if t["betting_open"]:
        current_multiplier = db.compute_multiplier(
            t["formula"], len(active), t["total_rounds"], t["current_round"]
        )

    winner = None
    payouts = []
    if t["winner_id"]:
        w = db.get_competitor(t["winner_id"])
        winner = {"id": w["id"], "name": w["name"]}
        payouts = db.get_payout_breakdown(t["winner_id"])

    return {
        "tournament": {
            "name": t["name"],
            "formula": t["formula"],
            "current_round": t["current_round"],
            "total_rounds": t["total_rounds"],
            "betting_open": bool(t["betting_open"]),
            "winner": winner,
        },
        "competitors": [dict(c) for c in all_competitors],
        "active_competitors": [dict(c) for c in active],
        "pool": pool,
        "odds": odds,
        "current_multiplier": current_multiplier,
        "payouts": payouts,
    }


# ---------------------------------------------------------------------------
# Public bets (for tracker detail views)

@app.get("/api/public/bets")
def public_bets():
    bets = db.get_all_bets()
    return [dict(b) for b in bets]


# Bet routes
# ---------------------------------------------------------------------------

@app.get("/api/bet/info")
def bet_info():
    """Everything the bet page needs to render."""
    t = db.get_tournament()
    if not t:
        return {"tournament": None}

    active = db.get_active_competitors()
    all_competitors = db.get_competitors()
    pool = db.get_pool_stats()

    current_multiplier = None
    if t["betting_open"]:
        current_multiplier = db.compute_multiplier(
            t["formula"], len(active), t["total_rounds"], t["current_round"]
        )

    bettor_options = [c["name"] for c in all_competitors] + ["Organizer"]

    # Per-competitor effective totals so the bet page can estimate the real
    # "if they win" payout (winner's backers split the whole pool by effective bet).
    eff_by_id = {o["id"]: o["effective_bet"] for o in db.get_competitor_odds()}

    return {
        "tournament": {
            "name": t["name"],
            "formula": t["formula"],
            "current_round": t["current_round"],
            "total_rounds": t["total_rounds"],
            "betting_open": bool(t["betting_open"]),
            "winner_id": t["winner_id"],
        },
        "active_competitors": [
            {"id": c["id"], "name": c["name"], "effective_bet": eff_by_id.get(c["id"], 0.0)}
            for c in active
        ],
        "bettor_options": bettor_options,
        "pool": pool,
        "current_multiplier": current_multiplier,
    }


@app.post("/api/bet/place")
def place_bet(body: BetRequest):
    t = db.get_tournament()
    if not t:
        raise HTTPException(status_code=400, detail="No tournament set up")
    if not t["betting_open"]:
        raise HTTPException(status_code=400, detail="Betting is currently closed")
    if t["winner_id"]:
        raise HTTPException(status_code=400, detail="Tournament is over")

    result = db.place_bet(body.bettor_name, body.competitor_id, body.amount)
    if result is None:
        raise HTTPException(status_code=400, detail="Could not place bet — check competitor and amount")

    competitor = db.get_competitor(body.competitor_id)
    pool = db.get_pool_stats()
    return {
        "ok": True,
        "bet_id": result["bet_id"],
        "bettor_name": body.bettor_name,
        "competitor_name": competitor["name"],
        "amount": result["amount"],
        "multiplier": result["multiplier"],
        "effective_bet": result["effective_bet"],
        "total_pool": pool["total_pool"],
    }
