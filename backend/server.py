from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime, timezone

import simulation as sim

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="OCC Sim API")
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("occ.api")


# ---------------- Request models ---------------- #
class AssignReq(BaseModel):
    crew_id: str
    force: bool = False


class TickReq(BaseModel):
    minutes: int = 30


class ResolveReq(BaseModel):
    action: str


class AdvisorReq(BaseModel):
    incident_id: Optional[str] = None
    question: Optional[str] = None


# ---------------- DB helpers ---------------- #
async def _load(game_id: str) -> dict:
    doc = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Game not found")
    return doc


async def _save(state: dict) -> None:
    await db.games.replace_one({"id": state["id"]}, state, upsert=True)


# ---------------- Routes ---------------- #
@api_router.get("/")
async def root():
    return {"service": "OCC Sim", "ok": True, "time": datetime.now(timezone.utc).isoformat()}


class NewGameReq(BaseModel):
    scenario: Optional[str] = "free_play"


@api_router.post("/sim/new")
async def create_new_game(body: NewGameReq | None = None):
    scenario = (body.scenario if body else "free_play") or "free_play"
    state = sim.new_game(scenario=scenario)
    await _save(state)
    return state


@api_router.get("/sim/{game_id}")
async def get_state(game_id: str):
    return await _load(game_id)


@api_router.get("/sim/{game_id}/roster_status")
async def roster_status(game_id: str):
    state = await _load(game_id)
    return sim.roster_completeness(state)


@api_router.post("/sim/{game_id}/check_assignment/{flight_id}")
async def precheck(game_id: str, flight_id: str, body: AssignReq):
    state = await _load(game_id)
    warnings = sim.check_assignment(state, flight_id, body.crew_id)
    return {"warnings": warnings, "has_critical": any(w["severity"] == "critical" for w in warnings)}


@api_router.post("/sim/{game_id}/assign/{flight_id}")
async def assign(game_id: str, flight_id: str, body: AssignReq):
    state = await _load(game_id)
    result = sim.assign_crew(state, flight_id, body.crew_id, force=body.force)
    if result["applied"]:
        await _save(state)
    return result


@api_router.post("/sim/{game_id}/unassign/{flight_id}/{crew_id}")
async def unassign(game_id: str, flight_id: str, crew_id: str):
    state = await _load(game_id)
    result = sim.unassign_crew(state, flight_id, crew_id)
    await _save(state)
    return result


@api_router.post("/sim/{game_id}/start_day")
async def start_day(game_id: str):
    state = await _load(game_id)
    result = sim.start_day(state)
    await _save(state)
    return {**result, "state": state}


@api_router.post("/sim/{game_id}/tick")
async def tick(game_id: str, body: TickReq):
    state = await _load(game_id)
    result = sim.tick(state, minutes=body.minutes)
    await _save(state)
    return {**result, "kpis": state["kpis"], "clock": state["clock"], "incidents": state["incidents"]}


@api_router.post("/sim/{game_id}/resolve/{incident_id}")
async def resolve(game_id: str, incident_id: str, body: ResolveReq):
    state = await _load(game_id)
    result = sim.resolve_incident(state, incident_id, body.action)
    await _save(state)
    return result


@api_router.post("/sim/{game_id}/end_day")
async def end_day(game_id: str):
    state = await _load(game_id)
    result = sim.end_day(state)
    await _save(state)
    return result


@api_router.post("/sim/{game_id}/auto_roster")
async def auto_roster(game_id: str):
    state = await _load(game_id)
    if state["phase"] != "ROSTER":
        raise HTTPException(status_code=400, detail="Auto-roster only available in ROSTER phase")
    result = sim.auto_roster(state)
    await _save(state)
    return result


@api_router.post("/sim/{game_id}/restart_day")
async def restart_day(game_id: str):
    state = await _load(game_id)
    result = sim.restart_day(state)
    await _save(state)
    return {**result, "state": state}


@api_router.post("/sim/{game_id}/next_day")
async def next_day(game_id: str):
    state = await _load(game_id)
    if state["phase"] != "DEBRIEF":
        raise HTTPException(status_code=400, detail="Must end the current day first")
    result = sim.advance_to_next_day(state)
    await _save(state)
    return {**result, "state": state}


@api_router.post("/sim/{game_id}/advisor")
async def advisor(game_id: str, body: AdvisorReq):
    state = await _load(game_id)
    summary = sim.summarize_state_for_advisor(state, focus_incident_id=body.incident_id)
    question = body.question or (
        "Given the operational state below, give a tactical recommendation in 3-6 short sentences. "
        "Be specific: name flights, suggest concrete recovery actions (callout standby, swap, delay, reroute, cancel), "
        "and call out the biggest legality / fatigue risk. Use airline operations control language."
    )

    try:
        from anthropic import AsyncAnthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY missing")
        anthropic_client = AsyncAnthropic(api_key=api_key)
        import json
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=(
                "You are 'OPS-ADVISOR', a senior airline operations control supervisor at Eaglewing International "
                "(simulation). You speak in concise, professional airline ops-control language. "
                "You reference EASA FTL concepts (FDP, rest, type rating) when relevant but always remind that this "
                "is a SIMULATION, not an official compliance tool. Keep answers under 120 words. "
                "Output plain text only (no markdown headings)."
            ),
            messages=[{
                "role": "user",
                "content": f"OPERATIONAL STATE:\n{json.dumps(summary, indent=2)}\n\nREQUEST: {question}",
            }],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        # Persist short advisor history
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "incident_id": body.incident_id,
            "question": question,
            "response": text,
        }
        state.setdefault("advisor_history", []).append(entry)
        # Keep last 20
        state["advisor_history"] = state["advisor_history"][-20:]
        await _save(state)
        return {"ok": True, "response": text, "summary": summary}
    except Exception as exc:
        logger.exception("Advisor failure")
        # Graceful fallback so UI never breaks
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "error": str(exc),
                "response": (
                    ">> SYS_MSG: Advisor offline. Recommend: triage open incidents by severity, "
                    "call out standby for crew gaps, accept short delays before cancellations, "
                    "and verify FDP/rest before any swap."
                ),
                "summary": summary,
            },
        )


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
