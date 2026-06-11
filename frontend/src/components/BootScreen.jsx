import React, { useEffect, useState } from "react";

const LOG_LINES = [
    { prefix: "[OK]",   text: "EGW OCC TERMINAL v0.9.4 :: warm boot",            color: "t-nominal" },
    { prefix: "[OK]",   text: "Loading FTL ruleset (EASA ORO.FTL.205, 210, 235)", color: "t-nominal" },
    { prefix: "[OK]",   text: "Aircraft fleet manifest (8 ac) .............. LOADED", color: "t-nominal" },
    { prefix: "[OK]",   text: "Crew roster pool (114 crew) .................. LOADED", color: "t-nominal" },
    { prefix: "[OK]",   text: "Standby pool initialised",                          color: "t-nominal" },
    { prefix: "[OK]",   text: "OPS-ADVISOR LLM channel ...................... ONLINE", color: "t-nominal" },
    { prefix: "[OK]",   text: "Day-of-Ops weather feed (sim) ............... NOMINAL", color: "t-nominal" },
    { prefix: "[WAIT]", text: "Awaiting Crew Controller input >>",                 color: "t-warn" },
];

const SCENARIOS = [
    {
        id: "free_play",
        label: "FREE PLAY",
        badge: "OPEN CAMPAIGN",
        accent: "var(--status-info)",
        accentBg: "rgba(0,229,255,0.07)",
        desc: "Open-ended campaign. Roll the days until you retire—or break the airline.",
        detail: "No fixed end. Dynamic disruptions. Your call every day.",
    },
    {
        id: "survive_7",
        label: "SURVIVE 7",
        badge: "CHALLENGE MODE",
        accent: "var(--status-warning)",
        accentBg: "rgba(255,193,7,0.07)",
        desc: "Fixed-seed challenge. Disruption escalates daily—storm midweek, AOG by day 7.",
        detail: "Final performance grade on exit. One seed, no restarts.",
    },
];

function useReducedMotion() {
    const [reduced, setReduced] = useState(
        () => window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
    useEffect(() => {
        const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
        const handler = (e) => setReduced(e.matches);
        mq.addEventListener("change", handler);
        return () => mq.removeEventListener("change", handler);
    }, []);
    return reduced;
}

export default function BootScreen({ onContinue, loading, onResume }) {
    const [shown, setShown] = useState(0);
    const [scenario, setScenario] = useState("free_play");
    const [hasSaved, setHasSaved] = useState(false);
    const [mounted, setMounted] = useState(false);
    const reducedMotion = useReducedMotion();

    useEffect(() => {
        const frame = requestAnimationFrame(() => setMounted(true));
        return () => cancelAnimationFrame(frame);
    }, []);

    useEffect(() => {
        if (reducedMotion) { setShown(LOG_LINES.length); return; }
        if (shown >= LOG_LINES.length) return;
        const t = setTimeout(() => setShown((s) => s + 1), 130);
        return () => clearTimeout(t);
    }, [shown, reducedMotion]);

    useEffect(() => {
        try { setHasSaved(!!localStorage.getItem("egw_occ_game_id")); }
        catch { setHasSaved(false); }
    }, []);

    const active = SCENARIOS.find((s) => s.id === scenario);

    return (
        <div
            className="relative h-full w-full flex flex-col overflow-hidden"
            data-testid="boot-screen"
            style={{
                backgroundImage:
                    "linear-gradient(rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.82) 40%, rgba(0,0,0,0.95) 100%), url(https://images.unsplash.com/photo-1757031299897-8014e806a3fb?crop=entropy&cs=srgb&fm=jpg&q=70)",
                backgroundSize: "cover",
                backgroundPosition: "center 30%",
            }}
        >
            {/* Scanline overlay */}
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 z-0"
                style={{
                    backgroundImage:
                        "repeating-linear-gradient(to bottom, transparent 0px, transparent 3px, rgba(255,255,255,0.012) 4px)",
                    backgroundSize: "100% 4px",
                }}
            />

            {/* Grid overlay */}
            <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-0 z-0 grid-strip opacity-30"
            />

            {/* ── Header strip ── */}
            <header className="relative z-10 border-b border-white/10 px-5 py-2.5 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-4">
                    <span className="kpi-num text-lg t-info" aria-label="Eaglewing Operations Control">EGW // OCC</span>
                    <span className="uppercase-wide hidden sm:block">Eaglewing Operations Control</span>
                </div>
                <div className="flex items-center gap-4">
                    <span
                        className="uppercase-wide"
                        style={{ color: "var(--status-warning)" }}
                    >
                        SIM-MODE
                    </span>
                    <span className="uppercase-wide hidden md:block">Not for operational use</span>
                </div>
            </header>

            {/* ── Main content ── */}
            <main className="relative z-10 flex-1 flex items-center justify-center px-5 py-6 overflow-auto">
                <div
                    className="w-full max-w-4xl"
                    style={{
                        opacity: mounted ? 1 : 0,
                        transform: mounted ? "none" : (reducedMotion ? "none" : "translateY(12px)"),
                        transition: reducedMotion ? "none" : "opacity 500ms ease, transform 500ms ease",
                    }}
                >
                    {/* Hero typography */}
                    <div className="mb-6">
                        <div className="label-key mb-2">EAGLEWING OPERATIONS CONTROL CENTER</div>
                        <h1
                            className="font-azeret leading-none tracking-tighter"
                            style={{
                                fontSize: "clamp(3.5rem, 10vw, 7rem)",
                                color: "var(--txt-primary)",
                                textWrap: "balance",
                            }}
                        >
                            CREW
                            <span className="t-info"> · </span>
                            CONTROL
                            <span className="t-info"> · </span>
                            SIM
                        </h1>
                        <p className="t-sec mt-3 max-w-xl text-sm leading-relaxed">
                            Hardcore mixed-fleet airline operations-control simulation. Plan the
                            roster, then survive sickness, weather, tech faults, and ATC flow as
                            duty Crew Controller. EASA&nbsp;/&nbsp;UK&nbsp;CAA-inspired rule checks.
                        </p>
                    </div>

                    {/* Two-column: boot log + scenario picker */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">

                        {/* Terminal boot log */}
                        <section aria-label="System boot log">
                            <div className="label-key mb-2">SYSTEM INITIALISATION</div>
                            <div
                                className="border border-white/10 bg-black/60 p-4 font-mono-jb text-xs"
                                style={{ minHeight: "176px" }}
                            >
                                {LOG_LINES.slice(0, shown).map((line, i) => (
                                    <div key={i} className={`mb-0.5 ${line.color}`}>
                                        <span className="t-muted select-none">{line.prefix}&nbsp;</span>
                                        {line.text}
                                    </div>
                                ))}
                                {shown < LOG_LINES.length && (
                                    <div className="cursor-blink t-info" aria-label="Loading…" />
                                )}
                            </div>
                        </section>

                        {/* Scenario selection */}
                        <section aria-label="Scenario selection">
                            <div className="label-key mb-2">SELECT SCENARIO</div>
                            <div className="flex flex-col gap-3" role="radiogroup" aria-label="Game scenario">
                                {SCENARIOS.map((s) => {
                                    const isActive = scenario === s.id;
                                    return (
                                        <button
                                            key={s.id}
                                            data-testid={`scenario-${s.id.replace("_", "-")}`}
                                            role="radio"
                                            aria-checked={isActive}
                                            onClick={() => setScenario(s.id)}
                                            className="text-left p-3 border cursor-pointer focus-visible:outline-none"
                                            style={{
                                                borderColor: isActive ? s.accent : "rgba(255,255,255,0.12)",
                                                background: isActive ? s.accentBg : "transparent",
                                                boxShadow: isActive
                                                    ? `inset 0 0 0 1px ${s.accent}22, 0 0 16px ${s.accent}11`
                                                    : "none",
                                                transition: "border-color 180ms, background 180ms, box-shadow 180ms",
                                            }}
                                            onFocus={(e) => {
                                                e.currentTarget.style.outline = `2px solid ${s.accent}`;
                                                e.currentTarget.style.outlineOffset = "2px";
                                            }}
                                            onBlur={(e) => {
                                                e.currentTarget.style.outline = "none";
                                            }}
                                        >
                                            <div className="flex items-baseline justify-between gap-2 mb-1">
                                                <span
                                                    className="font-azeret text-sm"
                                                    style={{ color: isActive ? s.accent : "var(--txt-primary)" }}
                                                >
                                                    {s.label}
                                                </span>
                                                <span
                                                    className="badge text-[9px]"
                                                    style={{
                                                        borderColor: s.accent,
                                                        color: s.accent,
                                                        opacity: isActive ? 1 : 0.45,
                                                    }}
                                                >
                                                    {s.badge}
                                                </span>
                                            </div>
                                            <p className="t-sec text-xs leading-snug">{s.desc}</p>
                                            {isActive && (
                                                <p
                                                    className="font-mono-jb text-[10px] mt-1.5"
                                                    style={{ color: s.accent, opacity: 0.7 }}
                                                >
                                                    {s.detail}
                                                </p>
                                            )}
                                        </button>
                                    );
                                })}
                            </div>
                        </section>
                    </div>

                    {/* CTA row */}
                    <div className="flex items-center gap-3 flex-wrap">
                        <button
                            data-testid="boot-start-btn"
                            className="btn btn-primary"
                            onClick={() => onContinue(scenario)}
                            disabled={loading}
                            aria-busy={loading}
                            aria-label={
                                loading
                                    ? "Initialising…"
                                    : scenario === "survive_7"
                                    ? "Start 7-day challenge"
                                    : "Start duty shift"
                            }
                            style={{ minWidth: "160px" }}
                        >
                            {loading
                                ? "INITIALISING…"
                                : scenario === "survive_7"
                                ? ">> START CHALLENGE"
                                : ">> START DUTY"}
                        </button>

                        {hasSaved && onResume && (
                            <button
                                data-testid="boot-resume-btn"
                                className="btn btn-ok"
                                onClick={onResume}
                                disabled={loading}
                                aria-label="Resume last saved campaign"
                            >
                                ▶ RESUME CAMPAIGN
                            </button>
                        )}

                        <span className="uppercase-wide flex-1">
                            {hasSaved
                                ? "Resume or start fresh—starting overwrites the save"
                                : scenario === "survive_7"
                                ? "7-day fixed-seed run · graded on exit"
                                : "Press start to spin up day 1"}
                        </span>
                    </div>
                </div>
            </main>

            {/* ── Footer strip ── */}
            <footer className="relative z-10 border-t border-white/10 px-5 py-2 flex items-center justify-between flex-shrink-0">
                <div className="flex items-center gap-4">
                    <span className="uppercase-wide">BUILD 26.05</span>
                    <span
                        className="uppercase-wide hidden sm:block"
                        style={{ color: "var(--status-nominal)" }}
                    >
                        ● SIMULATION
                    </span>
                </div>
                <div className="flex items-center gap-4">
                    <span className="uppercase-wide hidden sm:block">HUB LHR</span>
                    <span className="uppercase-wide">FLEET&nbsp;8 · CREW&nbsp;114</span>
                </div>
            </footer>
        </div>
    );
}
