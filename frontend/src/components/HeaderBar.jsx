import React from "react";

function fmtClock(iso) {
    if (!iso) return "--:--";
    return iso.slice(11, 16) + "Z";
}

function Kpi({ label, value, sub, tone, testid }) {
    const toneClass =
        tone === "good"
            ? "t-nominal"
            : tone === "warn"
              ? "t-warn"
              : tone === "crit"
                ? "t-crit"
                : tone === "info"
                  ? "t-info"
                  : "";
    return (
        <div className="px-4 py-2 border-r border-white/10 min-w-[120px]" data-testid={testid}>
            <div className="label-key">{label}</div>
            <div className={`kpi-num text-2xl ${toneClass}`}>{value}</div>
            {sub && <div className="uppercase-wide t-muted">{sub}</div>}
        </div>
    );
}

export default function HeaderBar({
    state,
    onTick,
    onEndDay,
    onResetGame,
    onRestartDay,
    ticking,
    playing,
    speed,
    onTogglePlay,
    onChangeSpeed,
    pausedForAircraft,
}) {
    if (!state) return null;
    const k = state.kpis;
    const otpTone = k.otp_pct >= 85 ? "good" : k.otp_pct >= 70 ? "warn" : "crit";
    // Completion factor is a separate number from OTP: a cancelled sector is
    // not a late sector. Real carriers live in the high nineties.
    const cf = k.completion_factor_pct ?? 100;
    const cfTone = cf >= 98 ? "good" : cf >= 94 ? "warn" : "crit";
    // Knock-on minutes are the currency every recovery lever trades in.
    const reactionaryMin = k.reactionary_min ?? 0;
    const reactionaryTone = reactionaryMin === 0 ? "good" : reactionaryMin < 240 ? "warn" : "crit";
    const breachTone = k.legality_breaches === 0 ? "good" : k.legality_breaches < 3 ? "warn" : "crit";
    const fatigueTone = k.fatigue_index < 40 ? "good" : k.fatigue_index < 70 ? "warn" : "crit";

    return (
        <div className="border-b border-white/10 bg-[#050505] flex items-stretch flex-wrap">
            <div className="px-5 py-2 border-r border-white/10 flex flex-col justify-center min-w-[230px]">
                <div className="label-key">EGW//OCC · DAY {state.day_number || 1}{state.is_challenge ? ` / ${state.total_days || 7}` : ""}</div>
                <div className="font-azeret text-lg tracking-tight">
                    EAGLEWING OPS CONTROL
                </div>
                <div className="uppercase-wide t-muted">
                    HUB LHR · SIM · {state.phase}
                </div>
            </div>

            <Kpi
                label="ZULU CLOCK"
                value={fmtClock(state.clock)}
                sub={
                    pausedForAircraft
                        ? "⛔ GROUNDED — DECISION REQUIRED"
                        : playing
                          ? `▶ PLAY ${["", "1×", "2×", "5×", "15×"][speed] || ""}`
                          : state.phase === "OPS"
                            ? "PAUSED"
                            : ""
                }
                tone={pausedForAircraft ? "crit" : "info"}
                testid="kpi-clock"
            />
            <Kpi label="OTP%" value={`${k.otp_pct.toFixed(0)}`} sub="ON-TIME PERFORMANCE" tone={otpTone} testid="kpi-otp" />
            <Kpi
                label="BREACHES"
                value={k.legality_breaches}
                sub={k.curfew_violations > 0 ? `LEGALITY · ${k.curfew_violations} CURFEW` : "LEGALITY"}
                tone={breachTone}
                testid="kpi-breach"
            />
            <Kpi label="FATIGUE IDX" value={k.fatigue_index} sub="FLEET AVG" tone={fatigueTone} testid="kpi-fatigue" />
            <Kpi
                label="COMPL. FACTOR"
                value={`${cf.toFixed(0)}`}
                sub="SECTORS OPERATED"
                tone={cfTone}
                testid="kpi-completion"
            />
            <Kpi
                label="KNOCK-ON"
                value={`${reactionaryMin}m`}
                sub={`REACTIONARY · $${((k.delay_cost_usd ?? 0) / 1000).toFixed(0)}k`}
                tone={reactionaryTone}
                testid="kpi-reactionary"
            />
            <Kpi label="COST USD" value={`${(k.cost_usd / 1000).toFixed(1)}k`} sub="OPS COST" tone="warn" testid="kpi-cost" />
            <Kpi label="PAX DISR." value={k.pax_disrupted} sub="PASSENGERS" tone="warn" testid="kpi-pax" />
            <Kpi label="SCORE" value={k.score} sub="DUTY POINTS" tone={k.score > 700 ? "good" : k.score > 400 ? "warn" : "crit"} testid="kpi-score" />

            <div className="flex-1" />

            <div className="flex items-center gap-2 px-4 py-2 border-l border-t border-white/10 flex-wrap">
                {state.phase === "OPS" && (
                    <>
                        {pausedForAircraft && (
                            <span className="badge t-crit" data-testid="paused-for-aircraft-badge">
                                ⛔ CLOCK FROZEN — RESOLVE THE GROUNDED TAIL
                            </span>
                        )}
                        <button
                            data-testid="speed-down-btn"
                            className="btn"
                            onClick={() => onChangeSpeed(Math.max(1, speed - 1))}
                            disabled={speed <= 1 || pausedForAircraft}
                            title="Slower"
                            aria-label="Decrease simulation speed"
                        >
                            ◀◀
                        </button>
                        <button
                            data-testid="play-pause-btn"
                            className={`btn ${playing ? "btn-warn" : "btn-ok"}`}
                            onClick={onTogglePlay}
                            aria-pressed={playing}
                            disabled={pausedForAircraft}
                        >
                            {playing ? "⏸ PAUSE" : "▶ PLAY"}
                            <span className="t-muted ml-2" aria-hidden="true">␣</span>
                        </button>
                        <button
                            data-testid="speed-up-btn"
                            className="btn"
                            onClick={() => onChangeSpeed(Math.min(4, speed + 1))}
                            disabled={speed >= 4 || pausedForAircraft}
                            title="Faster"
                            aria-label="Increase simulation speed"
                        >
                            ▶▶
                        </button>
                        <div className="flex border border-white/20" role="group" aria-label="Simulation speed">
                            {[
                                { id: 1, label: "1×" },
                                { id: 2, label: "2×" },
                                { id: 3, label: "5×" },
                                { id: 4, label: "15×" },
                            ].map((s) => (
                                <button
                                    key={s.id}
                                    data-testid={`speed-${s.id}`}
                                    onClick={() => onChangeSpeed(s.id)}
                                    aria-pressed={speed === s.id}
                                    aria-label={`Set speed to ${s.label}`}
                                    disabled={pausedForAircraft}
                                    className={`font-mono-jb uppercase text-[11px] tracking-widest px-3 py-2 border-r border-white/10 last:border-r-0 focus-ring-inset cursor-pointer ${
                                        speed === s.id
                                            ? "bg-[var(--status-info)] text-black"
                                            : "t-sec hover:bg-white/5"
                                    }`}
                                >
                                    {s.label}
                                </button>
                            ))}
                        </div>
                        <button
                            data-testid="tick-15-btn"
                            className="btn"
                            onClick={() => onTick(15)}
                            disabled={ticking || pausedForAircraft}
                        >
                            +15M
                            <span className="t-muted ml-2" aria-hidden="true">[</span>
                        </button>
                        <button
                            data-testid="tick-30-btn"
                            className="btn"
                            onClick={() => onTick(30)}
                            disabled={ticking || pausedForAircraft}
                        >
                            +30M
                            <span className="t-muted ml-2" aria-hidden="true">]</span>
                        </button>
                        <button
                            data-testid="tick-60-btn"
                            className="btn"
                            onClick={() => onTick(60)}
                            disabled={ticking || pausedForAircraft}
                        >
                            +60M
                        </button>
                        <button
                            data-testid="restart-day-btn"
                            className="btn btn-warn"
                            onClick={onRestartDay}
                            title="Restart current day, keep roster"
                        >
                            ↺ RESTART DAY
                        </button>
                        <button
                            data-testid="end-day-btn"
                            className="btn btn-warn"
                            onClick={onEndDay}
                        >
                            END DAY
                        </button>
                    </>
                )}
                {state.phase === "DEBRIEF" && (
                    <button
                        data-testid="new-game-btn"
                        className="btn btn-primary"
                        onClick={onResetGame}
                    >
                        NEW DUTY
                    </button>
                )}
            </div>
        </div>
    );
}
