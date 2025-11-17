"""
Database Schemas for the Gaming Platform

Each Pydantic model corresponds to a MongoDB collection. The collection name
is the lowercase of the class name (e.g., Team -> "team").
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

# Core domain models

class GamerUser(BaseModel):
    username: str = Field(..., description="Unique handle")
    display_name: Optional[str] = Field(None, description="Public display name")
    email: str = Field(..., description="Email address")
    country: str = Field(..., description="ISO country code or name")
    bio: Optional[str] = Field(None, description="Short bio")
    avatar_url: Optional[str] = Field(None, description="Profile image URL")
    streams: Optional[dict] = Field(
        default=None,
        description="Connected streaming accounts (e.g., {twitch, youtube, kick})",
    )

class Team(BaseModel):
    name: str = Field(..., description="Team name")
    game: str = Field(..., description="Primary game this team plays")
    country: str = Field(..., description="Country this team belongs to")
    captain_user_id: str = Field(..., description="User ID of the team captain")
    member_user_ids: List[str] = Field(default_factory=list, description="Team members' user IDs")
    achievements: List[str] = Field(default_factory=list, description="Public achievements")
    stats: dict = Field(
        default_factory=lambda: {
            "matches": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "points": 0,
        },
        description="Aggregated statistics",
    )

class Venue(BaseModel):
    name: str
    address: str
    city: Optional[str] = None
    country: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    admin_user_id: Optional[str] = Field(None, description="User ID of venue admin")

MatchFormat = Literal["BO1", "BO2", "BO3", "BO5"]

class Challenge(BaseModel):
    challenger_team_id: str
    opponent_team_id: str
    game: str
    country: str = Field(..., description="Match country restriction")
    proposed_datetime: Optional[datetime] = Field(None, description="Proposed start time (UTC)")
    format: MatchFormat = Field("BO3")
    venue_id: Optional[str] = None
    status: Literal[
        "proposed",
        "negotiating",
        "approved",
        "booked",
        "completed",
        "rejected",
        "cancelled",
    ] = "proposed"
    approvals: dict = Field(
        default_factory=lambda: {"challenger": False, "opponent": False},
        description="Per-team approvals",
    )
    notes: Optional[str] = None

class Booking(BaseModel):
    challenge_id: str
    venue_id: str
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    status: Literal["pending", "confirmed", "cancelled"] = "pending"

class Match(BaseModel):
    challenge_id: str
    venue_id: str
    game: str
    format: MatchFormat
    team_a_id: str
    team_b_id: str
    result: Optional[dict] = Field(
        default=None,
        description="Result payload e.g., {winner_team_id, scores: {a: x, b: y}}",
    )
    status: Literal["scheduled", "completed"] = "scheduled"
