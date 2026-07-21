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
}) {
    if (!state) return null;
    const k = state.kpis;
    const otpTone = k.otp_pct >= 85 ? "good" : k.otp_pct >= 70 ? "warn" : "crit";
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

            <Kpi label="ZULU CLOCK" value={fmtClock(state.clock)} sub={playing ? `▶ PLAY ${["", "1×", "2×", "5×", "15×"][speed] || ""}` : state.phase === "OPS" ? "PAUSED" : ""} tone="info" testid="kpi-clock" />
            <Kpi label="OTP%" value={`${k.otp_pct.toFixed(0)}`} sub="ON-TIME PERFORMANCE" tone={otpTone} testid="kpi-otp" />
            <Kpi
                label="BREACHES"
                value={k.legality_breaches}
                sub={k.curfew_violations > 0 ? `LEGALITY · ${k.curfew_violations} CURFEW` : "LEGALITY"}
                tone={breachTone}
                testid="kpi-breach"
            />
            <Kpi label="FATIGUE IDX" value={k.fatigue_index} sub="FLEET AVG" tone={fatigueTone} testid="kpi-fatigue" />
            <Kpi label="COST USD" value={`${(k.cost_usd / 1000).toFixed(1)}k`} sub="OPS COST" tone="warn" testid="kpi-cost" />
            <Kpi label="PAX DISR." value={k.pax_disrupted} sub="PASSENGERS" tone="warn" testid="kpi-pax" />
            <Kpi label="SCORE" value={k.score} sub="DUTY POINTS" tone={k.score > 700 ? "good" : k.score > 400 ? "warn" : "crit"} testid="kpi-score" />

            <div className="flex-1" />

            <div className="flex items-center gap-2 px-4 py-2 border-l border-t border-white/10 flex-wrap">
                {state.phase === "OPS" && (
                    <>
                        <button
                            data-testid="speed-down-btn"
                            className="btn"
                            onClick={() => onChangeSpeed(Math.max(1, speed - 1))}
                            disabled={speed <= 1}
                            title="Slower"
                        >
                            ◀◀
                        </button>
                        <button
                            data-testid="play-pause-btn"
                            className={`btn ${playing ? "btn-warn" : "btn-ok"}`}
                            onClick={onTogglePlay}
                        >
                            {playing ? "⏸ PAUSE" : "▶ PLAY"}
                        </button>
                        <button
                            data-testid="speed-up-btn"
                            className="btn"
                            onClick={() => onChangeSpeed(Math.min(4, speed + 1))}
                            disabled={speed >= 4}
                            title="Faster"
                        >
                            ▶▶
                        </button>
                        <div className="flex border border-white/20">
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
                                    className={`font-mono-jb uppercase text-[11px] tracking-widest px-3 py-2 border-r border-white/10 last:border-r-0 ${
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
                            disabled={ticking}
                        >
                            +15M
                        </button>
                        <button
                            data-testid="tick-30-btn"
                            className="btn"
                            onClick={() => onTick(30)}
                            disabled={ticking}
                        >
                            +30M
                        </button>
                        <button
                            data-testid="tick-60-btn"
                            className="btn"
                            onClick={() => onTick(60)}
                            disabled={ticking}
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
