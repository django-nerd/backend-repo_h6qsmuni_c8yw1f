import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import GamerUser, Team, Venue, Challenge, Booking, Match

app = FastAPI(title="Gaming Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Helpers
# -----------------------------

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")


def serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    result: Dict[str, Any] = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    if "_id" in doc:
        result["id"] = str(doc["_id"])
        result.pop("_id", None)
    return result


def serialize_list(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [serialize(d) for d in docs]


# -----------------------------
# Health
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "Gaming Platform API running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            _ = db.list_collection_names()
            response["database"] = "✅ Connected & Working"
            response["connection_status"] = "Connected"
            response["collections"] = _
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# -----------------------------
# Users
# -----------------------------

class CreateUserRequest(GamerUser):
    pass


@app.post("/users")
def create_user(payload: CreateUserRequest):
    user_id = create_document("gameruser", payload)
    doc = db["gameruser"].find_one({"_id": oid(user_id)})
    return serialize(doc)


# -----------------------------
# Venues
# -----------------------------

class CreateVenueRequest(Venue):
    pass


@app.post("/venues")
def create_venue(payload: CreateVenueRequest):
    venue_id = create_document("venue", payload)
    doc = db["venue"].find_one({"_id": oid(venue_id)})
    return serialize(doc)


@app.get("/venues")
def list_venues(country: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if country:
        filt["country"] = country
    docs = get_documents("venue", filt)
    return serialize_list(docs)


# -----------------------------
# Teams
# -----------------------------

class CreateTeamRequest(Team):
    pass


@app.post("/teams")
def create_team(payload: CreateTeamRequest):
    # Ensure members include captain
    if payload.captain_user_id and payload.captain_user_id not in payload.member_user_ids:
        payload.member_user_ids.append(payload.captain_user_id)
    team_id = create_document("team", payload)
    doc = db["team"].find_one({"_id": oid(team_id)})
    return serialize(doc)


@app.get("/teams")
def list_teams(country: Optional[str] = None, game: Optional[str] = None):
    filt: Dict[str, Any] = {}
    if country:
        filt["country"] = country
    if game:
        filt["game"] = game
    teams = get_documents("team", filt)
    return serialize_list(teams)


@app.get("/teams/{team_id}/stats")
def get_team_stats(team_id: str):
    team = db["team"].find_one({"_id": oid(team_id)})
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return serialize(team.get("stats", {}))


# -----------------------------
# Challenges & Negotiation
# -----------------------------

class ProposeChallengeRequest(BaseModel):
    challenger_team_id: str
    opponent_team_id: str
    game: str
    country: str
    proposed_datetime: Optional[datetime] = None
    format: str = Field("BO3", pattern="^(BO1|BO2|BO3|BO5)$")
    venue_id: Optional[str] = None
    notes: Optional[str] = None


@app.post("/challenges")
def propose_challenge(payload: ProposeChallengeRequest):
    # Validate teams exist and constraints
    t1 = db["team"].find_one({"_id": oid(payload.challenger_team_id)})
    t2 = db["team"].find_one({"_id": oid(payload.opponent_team_id)})
    if not t1 or not t2:
        raise HTTPException(status_code=400, detail="Both teams must exist")
    if t1["country"] != t2["country"] or t1["country"] != payload.country:
        raise HTTPException(status_code=400, detail="Teams must be from the same country")
    if t1["game"] != t2["game"] or t1["game"] != payload.game:
        raise HTTPException(status_code=400, detail="Both teams must play the same game")

    ch = Challenge(
        challenger_team_id=payload.challenger_team_id,
        opponent_team_id=payload.opponent_team_id,
        game=payload.game,
        country=payload.country,
        proposed_datetime=payload.proposed_datetime,
        format=payload.format,  # type: ignore
        venue_id=payload.venue_id,
        status="proposed",
        approvals={"challenger": False, "opponent": False},
        notes=payload.notes,
    )
    cid = create_document("challenge", ch)
    doc = db["challenge"].find_one({"_id": oid(cid)})
    return serialize(doc)


class NegotiateChallengeRequest(BaseModel):
    proposed_datetime: Optional[datetime] = None
    format: Optional[str] = Field(None, pattern="^(BO1|BO2|BO3|BO5)$")
    venue_id: Optional[str] = None
    notes: Optional[str] = None


@app.patch("/challenges/{challenge_id}")
def negotiate_challenge(challenge_id: str, payload: NegotiateChallengeRequest):
    ch = db["challenge"].find_one({"_id": oid(challenge_id)})
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")
    update: Dict[str, Any] = {"status": "negotiating"}
    if payload.proposed_datetime is not None:
        update["proposed_datetime"] = payload.proposed_datetime
    if payload.format is not None:
        update["format"] = payload.format
    if payload.venue_id is not None:
        update["venue_id"] = payload.venue_id
    if payload.notes is not None:
        update["notes"] = payload.notes
    # Reset approvals on any change
    update["approvals"] = {"challenger": False, "opponent": False}
    db["challenge"].update_one({"_id": oid(challenge_id)}, {"$set": update})
    doc = db["challenge"].find_one({"_id": oid(challenge_id)})
    return serialize(doc)


class ApproveRequest(BaseModel):
    team_role: str = Field(..., pattern="^(challenger|opponent)$")


@app.post("/challenges/{challenge_id}/approve")
def approve_challenge(challenge_id: str, payload: ApproveRequest):
    ch = db["challenge"].find_one({"_id": oid(challenge_id)})
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")
    approvals = ch.get("approvals", {"challenger": False, "opponent": False})
    approvals[payload.team_role] = True
    status = "approved" if approvals.get("challenger") and approvals.get("opponent") else ch.get("status", "proposed")
    db["challenge"].update_one({"_id": oid(challenge_id)}, {"$set": {"approvals": approvals, "status": status}})
    doc = db["challenge"].find_one({"_id": oid(challenge_id)})
    return serialize(doc)


# -----------------------------
# Booking flow
# -----------------------------

class CreateBookingRequest(BaseModel):
    venue_id: str
    start_datetime: datetime
    end_datetime: Optional[datetime] = None


@app.post("/challenges/{challenge_id}/book")
def create_booking_for_challenge(challenge_id: str, payload: CreateBookingRequest):
    ch = db["challenge"].find_one({"_id": oid(challenge_id)})
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if ch.get("status") not in ["approved", "negotiating", "proposed"]:
        raise HTTPException(status_code=400, detail="Challenge not eligible for booking")

    booking = Booking(
        challenge_id=challenge_id,
        venue_id=payload.venue_id,
        start_datetime=payload.start_datetime,
        end_datetime=payload.end_datetime,
        status="pending",
    )
    bid = create_document("booking", booking)
    db["challenge"].update_one({"_id": oid(challenge_id)}, {"$set": {"status": "booked", "venue_id": payload.venue_id}})
    doc = db["booking"].find_one({"_id": oid(bid)})
    return serialize(doc)


class ConfirmBookingRequest(BaseModel):
    confirm: bool = True


@app.post("/bookings/{booking_id}/confirm")
def confirm_booking(booking_id: str, payload: ConfirmBookingRequest):
    booking = db["booking"].find_one({"_id": oid(booking_id)})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    new_status = "confirmed" if payload.confirm else "cancelled"
    db["booking"].update_one({"_id": oid(booking_id)}, {"$set": {"status": new_status}})
    # Keep challenge in booked unless cancelled
    if new_status == "cancelled":
        db["challenge"].update_one({"_id": oid(booking["challenge_id"])}, {"$set": {"status": "approved"}})
    return serialize(db["booking"].find_one({"_id": oid(booking_id)}))


# -----------------------------
# Match result & stats update
# -----------------------------

class RecordResultRequest(BaseModel):
    challenge_id: str
    winner_team_id: str
    score_a: int
    score_b: int


@app.post("/matches/record")
def record_match_result(payload: RecordResultRequest):
    ch = db["challenge"].find_one({"_id": oid(payload.challenge_id)})
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")
    team_a = ch["challenger_team_id"]
    team_b = ch["opponent_team_id"]
    if payload.winner_team_id not in [team_a, team_b]:
        raise HTTPException(status_code=400, detail="Winner must be one of the teams in the challenge")

    match = Match(
        challenge_id=payload.challenge_id,
        venue_id=ch.get("venue_id", ""),
        game=ch["game"],
        format=ch.get("format", "BO3"),  # type: ignore
        team_a_id=team_a,
        team_b_id=team_b,
        result={"winner_team_id": payload.winner_team_id, "scores": {"a": payload.score_a, "b": payload.score_b}},
        status="completed",
    )
    mid = create_document("match", match)
    db["challenge"].update_one({"_id": oid(payload.challenge_id)}, {"$set": {"status": "completed"}})

    # Update team stats and points (simple Elo-like: win +3, loss 0, draw 1 each)
    def update_stats(team_id: str, won: bool, draw: bool = False):
        team = db["team"].find_one({"_id": oid(team_id)})
        if not team:
            return
        stats = team.get("stats", {"matches": 0, "wins": 0, "losses": 0, "draws": 0, "points": 0})
        stats["matches"] = stats.get("matches", 0) + 1
        if draw:
            stats["draws"] = stats.get("draws", 0) + 1
            stats["points"] = stats.get("points", 0) + 1
        elif won:
            stats["wins"] = stats.get("wins", 0) + 1
            stats["points"] = stats.get("points", 0) + 3
        else:
            stats["losses"] = stats.get("losses", 0) + 1
        db["team"].update_one({"_id": oid(team_id)}, {"$set": {"stats": stats}})

    if payload.score_a == payload.score_b:
        update_stats(team_a, False, True)
        update_stats(team_b, False, True)
    else:
        winner = payload.winner_team_id
        loser = team_b if winner == team_a else team_a
        update_stats(winner, True, False)
        update_stats(loser, False, False)

    return serialize(db["match"].find_one({"_id": oid(mid)}))


# -----------------------------
# Leaderboard
# -----------------------------

@app.get("/leaderboard")
def leaderboard(
    scope: str = Query("global", pattern="^(local|global)$"),
    game: Optional[str] = None,
    country: Optional[str] = None,
    limit: int = 20,
):
    filt: Dict[str, Any] = {}
    if game:
        filt["game"] = game
    if scope == "local":
        if not country:
            raise HTTPException(status_code=400, detail="Country is required for local leaderboard")
        filt["country"] = country
    teams = list(db["team"].find(filt))
    teams.sort(key=lambda t: (t.get("stats", {}).get("points", 0), t.get("stats", {}).get("wins", 0)), reverse=True)
    return [
        {
            "id": str(t["_id"]),
            "name": t.get("name"),
            "game": t.get("game"),
            "country": t.get("country"),
            "stats": t.get("stats", {}),
        }
        for t in teams[:limit]
    ]
