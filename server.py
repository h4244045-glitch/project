from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timezone
import os
import requests
import json
import logging
import uuid

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Safe ENV Parsing
raw_mongo_url = os.getenv('MONGO_URL', '').strip().strip('"').strip("'")
mongo_url = raw_mongo_url if (raw_mongo_url.startswith('mongodb://') or raw_mongo_url.startswith('mongodb+srv://')) else "mongodb://localhost:27017"
db_name = os.getenv('DB_NAME', 'globetrip_db').strip().strip('"').strip("'") or "globetrip_db"

client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

app = FastAPI(title="GlobeTrip Planner API")
api_router = APIRouter(prefix="/api")

# --- Models ---
class TripRequest(BaseModel):
    destination: str
    days: int = Field(default=3, ge=1, le=14)
    budget_inr: float = Field(..., description="Budget in INR (₹)")
    travelers: int = Field(default=1, ge=1)
    preferences: Optional[List[str]] = []
    preferred_ai: str = Field(default="gpt-4o", description="Options: gpt-4o, claude-3-5-sonnet")

class Hotel(BaseModel):
    name: str
    estimated_price_per_night_inr: float
    rating: float
    location: str
    photo_url: Optional[str] = None

class Activity(BaseModel):
    time: str
    title: str
    description: str
    estimated_cost_inr: float

class DayItinerary(BaseModel):
    day: int
    theme: str
    activities: List[Activity]

class TripItineraryResponse(BaseModel):
    trip_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    destination: str
    days: int
    total_budget_inr: float
    formatted_budget_inr: str
    hotels: List[Hotel]
    itinerary: List[DayItinerary]
    ai_model_used: str

class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# --- Helper Functions ---
def format_inr(amount: float) -> str:
    """Formats number into Indian Rupee format (e.g., ₹1,50,000)"""
    s = f"{int(amount)}"
    if len(s) <= 3:
        return f"₹{s}"
    last_three = s[-3:]
    other_digits = s[:-3]
    res = ""
    for i, digit in enumerate(reversed(other_digits)):
        if i > 0 and i % 2 == 0:
            res = "," + res
        res = digit + res
    return f"₹{res},{last_three}"

async def fetch_google_hotel_photo(hotel_name: str, location: str) -> Optional[str]:
    """Fetches real hotel image URL using Google Places API"""
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key or api_key == "your_google_places_api_key_here":
        return "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80"
    
    try:
        query = f"{hotel_name} {location}"
        search_url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={api_key}"
        res = requests.get(search_url, timeout=5).json()
        
        if res.get("results") and len(res["results"]) > 0:
            place = res["results"][0]
            if "photos" in place and len(place["photos"]) > 0:
                photo_ref = place["photos"][0]["photo_reference"]
                return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photo_reference={photo_ref}&key={api_key}"
    except Exception as e:
        logging.warning(f"Google Places API fetch failed: {e}")
    
    return "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=800&q=80"

# --- API Endpoints ---
@api_router.get("/")
async def root():
    return {"message": "GlobeTrip Planner API Running"}

@api_router.post("/generate-trip", response_model=TripItineraryResponse)
async def generate_trip(request: TripRequest):
    formatted_budget = format_inr(request.budget_inr)
    
    sample_hotels = [
        {
            "name": f"Grand Resort {request.destination.capitalize()}",
            "estimated_price_per_night_inr": round(request.budget_inr * 0.2, 2),
            "rating": 4.5,
            "location": f"Central {request.destination}"
        },
        {
            "name": f"Heritage Boutique Hotel",
            "estimated_price_per_night_inr": round(request.budget_inr * 0.12, 2),
            "rating": 4.2,
            "location": f"Old Town, {request.destination}"
        }
    ]

    enriched_hotels = []
    for h in sample_hotels:
        photo = await fetch_google_hotel_photo(h["name"], request.destination)
        enriched_hotels.append(Hotel(**h, photo_url=photo))

    itinerary = []
    for d in range(1, request.days + 1):
        itinerary.append(DayItinerary(
            day=d,
            theme=f"Exploring Highlights - Day {d}",
            activities=[
                Activity(
                    time="09:00 AM",
                    title="City Sightseeing Tour",
                    description="Visit key landmarks and local attractions.",
                    estimated_cost_inr=1500.0
                ),
                Activity(
                    time="01:00 PM",
                    title="Authentic Dining Experience",
                    description="Enjoy local culinary specialties.",
                    estimated_cost_inr=800.0
                )
            ]
        ))

    result = TripItineraryResponse(
        destination=request.destination,
        days=request.days,
        total_budget_inr=request.budget_inr,
        formatted_budget_inr=formatted_budget,
        hotels=enriched_hotels,
        itinerary=itinerary,
        ai_model_used=request.preferred_ai
    )

    doc = result.model_dump()
    await db.trips.insert_one(doc)

    return result

@api_router.get("/places/photo")
async def get_place_photo(query: str = Query(...)):
    photo_url = await fetch_google_hotel_photo(query, "")
    return {"query": query, "photo_url": photo_url}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.model_dump())
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    checks = await db.status_checks.find({}, {"_id": 0}).to_list(100)
    for check in checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return checks

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
