import React from "react";

function rating(score) {
    if (score >= 900) return { label: "GOLD", tone: "t-nominal", note: "Exceptional shift. Promoted to lead controller." };
    if (score >= 700) return { label: "GREEN", tone: "t-nominal", note: "Solid shift. Ops Manager nods approvingly." };
    if (score >= 500) return { label: "AMBER", tone: "t-warn", note: "Marginal shift. Debrief flagged for review." };
    return { label: "RED", tone: "t-crit", note: "Hard day. Roster Manager wants a word." };
}

export default function Debrief({ state, onNewGame, onNextDay, nextDayBusy }) {
    const k = state.kpis;
    const r = rating(k.score);
    const cancellations = state.flights.reduce((sum, f) => sum + (f.status === "cancelled" ? 1 : 0), 0);
    const dec = state.decisions_log || [];
    const ck = state.campaign_kpis || { days_completed: 0, per_day: [] };

    return (
        <div className="h-full flex flex-col" data-testid="debrief-view">
            <div className="px-6 py-5 border-b border-white/10 flex items-center justify-between">
                <div>
                    <div className="label-key">END OF DAY {state.day_number || 1} · DEBRIEF</div>
                    <div className="font-azeret text-3xl mt-1">CONTROLLER REPORT</div>
                </div>
                <div className="flex items-center gap-3">
                    {state.campaign_complete ? (
                        <button data-testid="debrief-new-game-btn" className="btn btn-primary" onClick={onNewGame}>
                            ↺ NEW CAMPAIGN
                        </button>
                    ) : (
                        <>
                            <button data-testid="next-day-btn" className="btn btn-primary" onClick={onNextDay} disabled={nextDayBusy}>
                                {nextDayBusy ? "ROLLING..." : `▶ DAY ${(state.day_number || 1) + 1}${state.is_challenge ? ` / ${state.total_days}` : ""}`}
                            </button>
                            <button data-testid="debrief-new-game-btn" className="btn btn-warn" onClick={onNewGame}>
                                ↺ NEW CAMPAIGN
                            </button>
                        </>
                    )}
                </div>
            </div>
            <div className="flex-1 scroll-area p-6 grid grid-cols-12 gap-6">
                {state.campaign_complete && state.final_grade && (
                    <div className="col-span-12 panel p-6" data-testid="final-grade-panel" style={{ borderTop: "2px solid var(--status-warning)" }}>
                        <div className="flex items-end justify-between">
                            <div>
                                <div className="label-key">SURVIVE-7 CHALLENGE · FINAL VERDICT</div>
                                <div className={`kpi-num text-6xl mt-2 ${state.final_grade.tone}`}>
                                    {state.final_grade.label}
                                </div>
                                <div className="t-sec mt-3 max-w-xl">{state.final_grade.note}</div>
                            </div>
                            <div className="grid grid-cols-2 gap-x-8 gap-y-2 font-mono-jb text-sm">
                                <div className="t-muted">DAYS COMPLETED</div><div className="t-info text-right">{state.final_grade.days_completed}</div>
                                <div className="t-muted">CUMULATIVE SCORE</div><div className="t-info text-right">{state.final_grade.total_score}</div>
                                <div className="t-muted">TOTAL BREACHES</div><div className={`text-right ${state.final_grade.total_breaches ? "t-crit" : "t-nominal"}`}>{state.final_grade.total_breaches}</div>
                                <div className="t-muted">AVG OTP</div><div className="t-info text-right">{state.final_grade.avg_otp_pct}%</div>
                            </div>
                        </div>
                    </div>
                )}
                <div className="col-span-4 panel p-6">
                    <div className="label-key">RATING</div>
                    <div className={`kpi-num text-7xl mt-2 ${r.tone}`}>{r.label}</div>
                    <div className="t-sec mt-3">{r.note}</div>
                    <div className="label-key mt-6">DAY SCORE</div>
                    <div className="kpi-num text-5xl mt-1">{k.score}</div>
                </div>
                <div className="col-span-8 panel p-6 grid grid-cols-3 gap-4">
                    <Stat label="OTP %" value={`${k.otp_pct.toFixed(1)}%`} tone={k.otp_pct >= 85 ? "t-nominal" : k.otp_pct >= 70 ? "t-warn" : "t-crit"} />
                    <Stat label="LEGALITY BREACHES" value={k.legality_breaches} tone={k.legality_breaches === 0 ? "t-nominal" : "t-crit"} />
                    <Stat label="FATIGUE INDEX" value={k.fatigue_index} tone={k.fatigue_index < 40 ? "t-nominal" : k.fatigue_index < 70 ? "t-warn" : "t-crit"} />
                    <Stat label="OPS COST USD" value={`$${k.cost_usd.toLocaleString()}`} tone="t-warn" />
                    <Stat label="PAX DISRUPTED" value={k.pax_disrupted} tone="t-warn" />
                    <Stat label="CANCELLATIONS" value={cancellations} tone={cancellations === 0 ? "t-nominal" : "t-crit"} />
                </div>

                <div className="col-span-12 panel p-6" data-testid="campaign-kpis">
                    <div className="flex items-end justify-between mb-4">
                        <div>
                            <div className="label-key">CAMPAIGN TO DATE</div>
                            <div className="font-azeret text-xl mt-1">{ck.days_completed} DAY{ck.days_completed === 1 ? "" : "S"} COMPLETED · DAY {state.day_number || 1} IN DEBRIEF</div>
                        </div>
                        <div className="uppercase-wide t-sec">
                            CUMULATIVE SCORE <span className="kpi-num t-info ml-2 text-2xl">{ck.total_score}</span>
                        </div>
                    </div>
                    <div className="grid grid-cols-4 gap-4">
                        <Stat label="AVG OTP" value={`${ck.avg_otp_pct?.toFixed?.(1) || "0"}%`} tone="t-info" />
                        <Stat label="TOTAL BREACHES" value={ck.total_breaches || 0} tone={ck.total_breaches > 0 ? "t-crit" : "t-nominal"} />
                        <Stat label="TOTAL COST" value={`$${(ck.total_cost_usd || 0).toLocaleString()}`} tone="t-warn" />
                        <Stat label="PAX DISRUPTED" value={ck.total_pax_disrupted || 0} tone="t-warn" />
                    </div>
                    {ck.per_day && ck.per_day.length > 0 && (
                        <div className="mt-5">
                            <div className="label-key mb-2">DAY-BY-DAY</div>
                            <table className="w-full font-mono-jb text-xs">
                                <thead className="uppercase-wide t-muted">
                                    <tr>
                                        <th className="text-left py-1 pr-4">DAY</th>
                                        <th className="text-right py-1 pr-4">SCORE</th>
                                        <th className="text-right py-1 pr-4">OTP%</th>
                                        <th className="text-right py-1 pr-4">BREACH</th>
                                        <th className="text-right py-1">COST</th>
                                    </tr>
                                </thead>
                                <tbody className="zebra">
                                    {ck.per_day.map((d) => (
                                        <tr key={d.day} className="border-b border-white/[0.04]">
                                            <td className="py-1 pr-4 t-info">D{d.day}</td>
                                            <td className="py-1 pr-4 text-right">{d.score}</td>
                                            <td className="py-1 pr-4 text-right">{d.otp?.toFixed?.(0)}</td>
                                            <td className={`py-1 pr-4 text-right ${d.breaches ? "t-crit" : "t-nominal"}`}>{d.breaches}</td>
                                            <td className="py-1 text-right t-warn">${d.cost?.toLocaleString?.()}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                <div className="col-span-12 panel p-6">
                    <div className="label-key">DAY {state.day_number || 1} DECISIONS LOG ({dec.length})</div>
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
