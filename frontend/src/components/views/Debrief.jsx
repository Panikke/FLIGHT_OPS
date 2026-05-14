import React from "react";

function rating(score) {
    if (score >= 900) return { label: "GOLD", tone: "t-nominal", note: "Exceptional shift. Promoted to lead controller." };
    if (score >= 700) return { label: "GREEN", tone: "t-nominal", note: "Solid shift. Ops Manager nods approvingly." };
    if (score >= 500) return { label: "AMBER", tone: "t-warn", note: "Marginal shift. Debrief flagged for review." };
    return { label: "RED", tone: "t-crit", note: "Hard day. Roster Manager wants a word." };
}

export default function Debrief({ state, onNewGame }) {
    const k = state.kpis;
    const r = rating(k.score);
    const breaches = state.flights.reduce((sum, f) => sum + (f.status === "cancelled" ? 1 : 0), 0);
    const dec = state.decisions_log || [];

    return (
        <div className="h-full flex flex-col" data-testid="debrief-view">
            <div className="px-6 py-5 border-b border-white/10 flex items-center justify-between">
                <div>
                    <div className="label-key">END OF DAY · DEBRIEF</div>
                    <div className="font-azeret text-3xl mt-1">CONTROLLER REPORT</div>
                </div>
                <button data-testid="debrief-new-game-btn" className="btn btn-primary" onClick={onNewGame}>
                    ▶ NEW DUTY
                </button>
            </div>
            <div className="flex-1 scroll-area p-6 grid grid-cols-12 gap-6">
                <div className="col-span-4 panel p-6">
                    <div className="label-key">RATING</div>
                    <div className={`kpi-num text-7xl mt-2 ${r.tone}`}>{r.label}</div>
                    <div className="t-sec mt-3">{r.note}</div>
                    <div className="label-key mt-6">FINAL SCORE</div>
                    <div className="kpi-num text-5xl mt-1">{k.score}</div>
                </div>
                <div className="col-span-8 panel p-6 grid grid-cols-3 gap-4">
                    <Stat label="OTP %" value={`${k.otp_pct.toFixed(1)}%`} tone={k.otp_pct >= 85 ? "t-nominal" : k.otp_pct >= 70 ? "t-warn" : "t-crit"} />
                    <Stat label="LEGALITY BREACHES" value={k.legality_breaches} tone={k.legality_breaches === 0 ? "t-nominal" : "t-crit"} />
                    <Stat label="FATIGUE INDEX" value={k.fatigue_index} tone={k.fatigue_index < 40 ? "t-nominal" : k.fatigue_index < 70 ? "t-warn" : "t-crit"} />
                    <Stat label="OPS COST USD" value={`$${k.cost_usd.toLocaleString()}`} tone="t-warn" />
                    <Stat label="PAX DISRUPTED" value={k.pax_disrupted} tone="t-warn" />
                    <Stat label="CANCELLATIONS" value={breaches} tone={breaches === 0 ? "t-nominal" : "t-crit"} />
                </div>

                <div className="col-span-12 panel p-6">
                    <div className="label-key">DECISIONS LOG ({dec.length})</div>
                    <div className="mt-3 font-mono-jb text-xs scroll-area max-h-[280px]">
                        {dec.length === 0 && <div className="t-muted">No decisions recorded.</div>}
                        {dec.map((d, i) => (
                            <div key={i} className="flex gap-4 py-1 border-b border-white/[0.04]">
                                <span className="t-muted">{d.ts.slice(11, 16)}Z</span>
                                <span className="t-info">{d.incident_id}</span>
                                <span>{d.action.toUpperCase()}</span>
                                <span className="t-warn ml-auto">${d.cost_usd?.toLocaleString() || 0}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

function Stat({ label, value, tone }) {
    return (
        <div>
            <div className="label-key">{label}</div>
            <div className={`kpi-num text-3xl mt-1 ${tone}`}>{value}</div>
        </div>
    );
}
