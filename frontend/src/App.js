import React, { useEffect, useState, useCallback } from "react";
import "@/App.css";
import { api } from "./api";
import BootScreen from "./components/BootScreen";
import HeaderBar from "./components/HeaderBar";
import Sidebar from "./components/Sidebar";
import RosterBoard from "./components/views/RosterBoard";
import FlightTimeline from "./components/views/FlightTimeline";
import IncidentQueue from "./components/views/IncidentQueue";
import CrewPanel from "./components/views/CrewPanel";
import AdvisorPanel from "./components/views/AdvisorPanel";
import RegsHelp from "./components/views/RegsHelp";
import Debrief from "./components/views/Debrief";
import AssignModal from "./components/AssignModal";

const STORAGE_KEY = "egw_occ_game_id";

function App() {
    const [state, setState] = useState(null);
    const [view, setView] = useState("roster");
    const [loading, setLoading] = useState(false);
    const [assignTarget, setAssignTarget] = useState(null);
    const [ticking, setTicking] = useState(false);
    const [advisorBusy, setAdvisorBusy] = useState(false);
    const [advisorLast, setAdvisorLast] = useState(null);
    const [toast, setToast] = useState(null);
    const [playing, setPlaying] = useState(false);
    const [speed, setSpeed] = useState(2); // 1=1×, 2=2×, 3=5×, 4=15×
    const [nextDayBusy, setNextDayBusy] = useState(false);

    // Restore prior session if exists
    useEffect(() => {
        const id = localStorage.getItem(STORAGE_KEY);
        if (id) {
            api.getState(id)
                .then((s) => setState(s))
                .catch(() => localStorage.removeItem(STORAGE_KEY));
        }
    }, []);

    useEffect(() => {
        if (!toast) return;
        const t = setTimeout(() => setToast(null), 4500);
        return () => clearTimeout(t);
    }, [toast]);

    const refresh = useCallback(async () => {
        if (!state?.id) return;
        const s = await api.getState(state.id);
        setState(s);
    }, [state?.id]);

    async function startNew(scenario = "free_play") {
        setLoading(true);
        try {
            const s = await api.newGame(scenario);
            setState(s);
            localStorage.setItem(STORAGE_KEY, s.id);
            setView("roster");
        } finally {
            setLoading(false);
        }
    }

    async function tick(minutes) {
        if (!state?.id || state.phase !== "OPS") return;
        setTicking(true);
        try {
            const res = await api.tick(state.id, minutes);
            await refresh();
            if (res.new_incidents && res.new_incidents.length > 0) {
                setToast(`▶ ${res.new_incidents.length} new incident(s) at ${res.clock.slice(11, 16)}Z`);
                setPlaying(false); // auto-pause on new incident
                setView("incidents");
            }
        } catch (e) {
            setPlaying(false);
            setToast(`⚠ TICK FAILED: ${e?.message || "backend error"} — auto-paused`);
        } finally {
            setTicking(false);
        }
    }

    // Auto-advance loop while playing
    useEffect(() => {
        if (!playing || state?.phase !== "OPS") return;
        const SPEED_MAP = {
            1: { interval: 1500, minutes: 5 },     // 5 sim min / 1.5s   = 200×
            2: { interval: 1200, minutes: 15 },    // 15 sim min / 1.2s  = 750×
            3: { interval: 1000, minutes: 30 },    // 30 sim min / 1s    = 1800×
            4: { interval: 900, minutes: 60 },     // 60 sim min / 0.9s  = 4000×
        };
        const cfg = SPEED_MAP[speed] || SPEED_MAP[2];
        let cancelled = false;
        const loop = async () => {
            if (cancelled) return;
            if (ticking) return;
            await tick(cfg.minutes);
        };
        const t = setInterval(loop, cfg.interval);
        return () => {
            cancelled = true;
            clearInterval(t);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playing, speed, state?.phase, state?.id]);

    // Stop playing whenever there are open incidents (forces operator decision)
    useEffect(() => {
        if (!state) return;
        const openCount = state.incidents.filter((i) => i.status === "open").length;
        if (openCount > 0 && playing) setPlaying(false);
    }, [state, playing]);

    async function resolveIncident(iid, action) {
        await api.resolve(state.id, iid, action);
        await refresh();
    }

    async function endDay() {
        await api.endDay(state.id);
        await refresh();
        setView("debrief");
    }

    async function restartDay() {
        if (!state?.id) return;
        // Optional confirmation
        if (!window.confirm("RESTART DAY — clock back to 04:00Z, incidents and decisions cleared. Roster kept. Continue?")) return;
        setPlaying(false);
        await api.restartDay(state.id);
        await refresh();
        setView("incidents");
        setToast("▶ DAY RESTARTED · clock back to 04:00Z");
    }

    async function startDay() {
        await api.startDay(state.id);
        await refresh();
        setView("incidents");
    }

    async function askAdvisor(incidentId, question) {
        setAdvisorBusy(true);
        try {
            const res = await api.advisor(state.id, { incident_id: incidentId, question });
            setAdvisorLast(res.response);
            await refresh();
            setView("advisor");
        } catch (e) {
            setAdvisorLast("Advisor channel offline.");
        } finally {
            setAdvisorBusy(false);
        }
    }

    async function newGame() {
        localStorage.removeItem(STORAGE_KEY);
        setState(null);
    }

    function exitToMenu() {
        // Preserve saved campaign in localStorage so the user can resume from boot
        if (state && state.phase === "OPS") {
            if (!window.confirm("Exit to menu? The current day is in progress — it will be saved and you can RESUME from the boot screen.")) return;
        }
        setPlaying(false);
        setView("roster");
        setState(null);
    }

    async function resumeGame() {
        const id = localStorage.getItem(STORAGE_KEY);
        if (!id) return;
        try {
            const s = await api.getState(id);
            setState(s);
            setView(s.phase === "DEBRIEF" ? "debrief" : s.phase === "OPS" ? "incidents" : "roster");
        } catch {
            localStorage.removeItem(STORAGE_KEY);
        }
    }

    async function nextDay() {
        if (!state?.id) return;
        setNextDayBusy(true);
        try {
            const res = await api.nextDay(state.id);
            await refresh();
            setView("roster");
            if (res.pre_rostered_returns > 0) {
                setToast(`▶ DAY ${res.day_number} · ${res.pre_rostered_returns} long-haul return(s) auto-rostered with yesterday's crew`);
            } else {
                setToast(`▶ DAY ${res.day_number} commenced`);
            }
        } catch (e) {
            setToast(`⚠ Failed to roll day: ${e?.message}`);
        } finally {
            setNextDayBusy(false);
        }
    }

    if (!state) {
        return (
            <div className="App">
                <BootScreen onContinue={startNew} loading={loading} onResume={resumeGame} />
            </div>
        );
    }

    const openIncidentCount = state.incidents.filter((i) => i.status === "open").length;
    const rosterIncomplete = state.flights.filter((f) => {
        const req = f.required_crew;
        const total = req.CP + req.FO + req.SC + req.CC;
        return f.assigned_crew_ids.length < total;
    }).length;

    const showView = state.phase === "DEBRIEF" ? "debrief" : view;

    return (
        <div className="App">
            <HeaderBar
                state={state}
                onTick={tick}
                onEndDay={endDay}
                onResetGame={newGame}
                onRestartDay={restartDay}
                ticking={ticking}
                playing={playing}
                speed={speed}
                onTogglePlay={() => setPlaying((p) => !p)}
                onChangeSpeed={(s) => setSpeed(s)}
            />
            <div className="flex-1 flex overflow-hidden">
                <Sidebar
                    active={showView}
                    onSelect={setView}
                    state={state}
                    openIncidentCount={openIncidentCount}
                    rosterIncomplete={rosterIncomplete}
                    onExitToMenu={exitToMenu}
                />
                <div className="flex-1 overflow-hidden">
                    {showView === "roster" && (
                        <RosterBoard
                            state={state}
                            onOpenAssign={(f) => setAssignTarget(f)}
                            onStartDay={startDay}
                        />
                    )}
                    {showView === "timeline" && <FlightTimeline state={state} />}
                    {showView === "incidents" && (
                        <IncidentQueue
                            state={state}
                            onResolve={resolveIncident}
                            onAskAdvisor={(iid) => askAdvisor(iid, null)}
                        />
                    )}
                    {showView === "crew" && <CrewPanel state={state} />}
                    {showView === "advisor" && (
                        <AdvisorPanel
                            state={state}
                            busy={advisorBusy}
                            lastResponse={advisorLast}
                            onAsk={(q) => askAdvisor(null, q)}
                        />
                    )}
                    {showView === "regs" && <RegsHelp />}
                    {showView === "debrief" && (
                        <Debrief
                            state={state}
                            onNewGame={newGame}
                            onNextDay={nextDay}
                            nextDayBusy={nextDayBusy}
                        />
                    )}
                </div>
            </div>

            {assignTarget && (
                <AssignModal
                    state={state}
                    flight={state.flights.find((f) => f.id === assignTarget.id) || assignTarget}
                    onClose={() => setAssignTarget(null)}
                    onAssigned={() => refresh()}
                />
            )}

            {toast && (
                <div
                    data-testid="toast"
                    className="fixed bottom-6 right-6 panel px-4 py-3 z-40"
                    style={{ borderTop: "2px solid var(--status-warning)" }}
                >
                    <div className="label-key t-warn">ALERT</div>
                    <div className="font-mono-jb text-xs mt-1">{toast}</div>
                </div>
            )}
        </div>
    );
}

export default App;
