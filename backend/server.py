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
    # Commander's discretion (ORO.FTL.205(f)) — legal within its cap, unlike
    # `force`, which books a real legality breach.
    discretion: bool = False


class TickReq(BaseModel):
    minutes: int = 30


class ResolveReq(BaseModel):
    action: str


class AdvisorReq(BaseModel):
    incident_id: Optional[str] = None
    question: Optional[str] = None


class DayOffReq(BaseModel):
    day: int
    off: bool = True


class AircraftReq(BaseModel):
    reg: str


class ResetToZeroReq(BaseModel):
    pairing_ids: list[str]


class DisposeReq(BaseModel):
    action: str


# ---------------- DB helpers ---------------- #
async def _load(game_id: str) -> dict:
    doc = await db.games.find_one({"id": game_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Game not found")
    # Engine constants the UI needs in order to show the player the same
    # thresholds the rules use — injected on every read so a saved game can
    # never drift from the engine it is running on.
    doc["config"] = {
        "escalation_after_min": sim.ESCALATION_AFTER_MIN,
        "escalation_extra_delay_min": sim.ESCALATION_EXTRA_DELAY_MIN,
        "min_turnaround_min": sim.MIN_TURNAROUND_MIN,
        "delay_cost_per_min_usd": sim.DELAY_COST_PER_MIN_USD,
        "target_completion_factor_pct": sim.TARGET_COMPLETION_FACTOR_PCT,
    }
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


@api_router.get("/sim/{game_id}/irregularities")
async def irregularities(game_id: str):
    """The problem monitor: what is wrong right now by the rules, as opposed
    to what has happened to the player by chance."""
    state = await _load(game_id)
    full = sim.crew_irregularities_full(state)
    items = full["irregularities"]
    return {
        **full,
        "critical": sum(1 for i in items if i["severity"] == "critical"),
        "warning": sum(1 for i in items if i["severity"] == "warning"),
        "advisory": sum(1 for i in items if i["severity"] == "advisory"),
    }


@api_router.get("/sim/{game_id}/crew_disposition")
async def crew_disposition(game_id: str):
    """The disposition desk: every crew who is not where they need to be, and
    what can be done about each of them."""
    state = await _load(game_id)
    rows = sim.crew_disposition(state)
    return {
        "disposition": rows,
        "handled_today": rows[0]["handled_today"] if rows else 0,
        "stranded": sum(1 for r in rows if r["at"] != r["base"]),
        "unreachable_duty": sum(
            1 for r in rows if r["next_duty"] and not r["next_duty"]["reachable"]),
    }


@api_router.post("/sim/{game_id}/crew/{crew_id}/dispose")
async def dispose_crew(game_id: str, crew_id: str, body: DisposeReq):
    state = await _load(game_id)
    result = sim.dispose_crew(state, crew_id, body.action)
    if result.get("applied"):
        await _save(state)
    return result


@api_router.post("/sim/{game_id}/crew/{crew_id}/preview_dispose")
async def preview_dispose_crew(game_id: str, crew_id: str, body: DisposeReq):
    state = await _load(game_id)
    return sim.preview_crew_disposition(state, crew_id, body.action)


@api_router.get("/sim/{game_id}/crew_roster")
async def crew_roster(game_id: str):
    state = await _load(game_id)
    return sim.crew_roster(state)


@api_router.post("/sim/{game_id}/crew/{crew_id}/day_off")
async def set_day_off(game_id: str, crew_id: str, body: DayOffReq):
    state = await _load(game_id)
    result = sim.set_day_off(state, crew_id, body.day, off=body.off)
    if result.get("ok"):
        await _save(state)
    return result


@api_router.get("/sim/{game_id}/aircraft_control")
async def aircraft_control(game_id: str):
    state = await _load(game_id)
    return sim.aircraft_control(state)


@api_router.post("/sim/{game_id}/check_aircraft/{pairing_id}")
async def check_aircraft(game_id: str, pairing_id: str, body: AircraftReq):
    state = await _load(game_id)
    warnings = sim.check_aircraft_assignment(state, pairing_id, body.reg)
    return {"warnings": warnings, "has_critical": any(w["severity"] == "critical" for w in warnings)}


@api_router.post("/sim/{game_id}/assign_aircraft/{pairing_id}")
async def assign_aircraft(game_id: str, pairing_id: str, body: AircraftReq):
    state = await _load(game_id)
    result = sim.assign_aircraft(state, pairing_id, body.reg)
    if result.get("applied"):
        # A re-tail during ops can change the knock-on delay picture (the tail's
        # rotation membership changed), so rebuild reactionary delay from its
        # non-reactionary baseline before re-propagating and re-scoring — a
        # stale knock-on from the old tail assignment must not survive the
        # swap that removed its cause.
        if state.get("phase") == "OPS":
            sim.reset_reactionary_delays(state)
            result["reactionary_delays"] = sim._log_cascade(
                state, sim.propagate_reactionary_delays(state), "aircraft_change", pairing_id)
            sim._recompute_kpis(state)
            result["kpis"] = state["kpis"]
        await _save(state)
    return result


@api_router.post("/sim/{game_id}/check_ferry/{pairing_id}")
async def check_ferry(game_id: str, pairing_id: str, body: AircraftReq):
    state = await _load(game_id)
    # Superset of the old {warnings, has_critical} shape — also carries the
    # positioning flight's route and what it will cost, so the desk can price
    # the ferry before dispatching it.
    return sim.preview_ferry(state, pairing_id, body.reg)


@api_router.post("/sim/{game_id}/ferry_aircraft/{pairing_id}")
async def ferry_aircraft(game_id: str, pairing_id: str, body: AircraftReq):
    state = await _load(game_id)
    result = sim.ferry_spare_aircraft(state, pairing_id, body.reg)
    if result.get("applied"):
        result["kpis"] = state["kpis"]
        await _save(state)
    return result


@api_router.post("/sim/{game_id}/preview_reset_to_zero")
async def preview_reset_to_zero(game_id: str, body: ResetToZeroReq):
    state = await _load(game_id)
    return sim.preview_reset_to_zero(state, body.pairing_ids)


@api_router.post("/sim/{game_id}/reset_to_zero")
async def reset_to_zero(game_id: str, body: ResetToZeroReq):
    state = await _load(game_id)
    result = sim.reset_to_zero(state, body.pairing_ids)
    if result.get("applied"):
        await _save(state)
    return result


@api_router.post("/sim/{game_id}/check_assignment/{flight_id}")
async def precheck(game_id: str, flight_id: str, body: AssignReq):
    state = await _load(game_id)
    warnings = sim.check_assignment(state, flight_id, body.crew_id)
    # The desk needs to know whether the commander could legally take this on
    # discretion before it offers a blanket override.
    return {"warnings": warnings,
            "has_critical": any(w["severity"] == "critical" for w in warnings),
            "discretion": sim.discretion_available(state, flight_id, body.crew_id)}


@api_router.post("/sim/{game_id}/assign/{flight_id}")
async def assign(game_id: str, flight_id: str, body: AssignReq):
    state = await _load(game_id)
    result = sim.assign_crew(state, flight_id, body.crew_id, force=body.force,
                             discretion=body.discretion)
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
            model="claude-sonnet-5",
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
        # Graceful fallback so the UI never breaks — but name the cause. A
        # missing API key used to render identically to a broken feature.
        missing_key = not os.environ.get("ANTHROPIC_API_KEY")
        if missing_key:
            reason = (
                ">> SYS_MSG: OPS-ADVISOR OFFLINE — no ANTHROPIC_API_KEY configured. "
                "Add a key to backend/.env and restart the backend to bring the advisor online."
            )
        else:
            reason = f">> SYS_MSG: OPS-ADVISOR OFFLINE — {exc}"
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "error": str(exc),
                "offline_reason": "missing_api_key" if missing_key else "upstream_error",
                "response": (
                    f"{reason}"
                    "\n\nFALLBACK GUIDANCE: triage open incidents by severity, "
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
