import React, { useState } from "react";

const KIND_LABEL = {
    CREW_SICK: "CREW SICKNESS",
    LATE_REPORT: "LATE REPORT",
    WEATHER: "WX DISRUPT",
    TECH: "TECH / MEL",
    ATC_FLOW: "ATC FLOW",
    CREW_HOURS: "CREW OUT OF HOURS",
};

const DEFAULT_ESCALATION_MIN = 60;

/** Minutes until an untouched incident escalates, or null once it already has. */
function minutesToEscalation(inc, state) {
    if (inc.status !== "open" || inc.escalated || !inc.raised_at) return null;
    const limit = state.config?.escalation_after_min ?? DEFAULT_ESCALATION_MIN;
    const elapsed = (new Date(state.clock) - new Date(inc.raised_at)) / 60000;
    return Math.max(0, Math.round(limit - elapsed));
}

/** Blocking first, then already-escalated, then whatever burns down soonest.
 *  A live queue has to answer "what do I deal with next", not "what arrived
 *  last" — an escalating major must never sit below three resolved minors. */
function triageOrder(inc, state) {
    if (inc.status === "resolved") return [3, 0];
    if (inc.requires_aircraft_decision) return [0, 0];
    if (inc.escalated) return [1, 0];
    return [2, minutesToEscalation(inc, state) ?? 999];
}

export default function IncidentQueue({ state, onResolve, onAskAdvisor, onOpenAircraftControl }) {
    // A live queue opens on what still needs work, not on a history of it.
    const [filter, setFilter] = useState("OPEN");
    const incs = state.incidents
        .filter((i) =>
            filter === "OPEN" ? i.status === "open" : filter === "ALL" ? true : i.status === "resolved"
        )
        .sort((a, b) => {
            const [ga, ta] = triageOrder(a, state);
            const [gb, tb] = triageOrder(b, state);
            return ga - gb || ta - tb;
        });
    const blocking = state.incidents.filter((i) => i.status === "open" && i.requires_aircraft_decision);

    return (
        <div className="h-full flex flex-col" data-testid="incident-queue">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">INCIDENT QUEUE</div>
                    <div className="font-azeret text-lg">LIVE DISRUPTIONS</div>
                </div>
                <div className="flex-1" />
                {["OPEN", "RESOLVED", "ALL"].map((f) => (
                    <button
                        key={f}
                        data-testid={`inc-filter-${f}`}
                        className={`btn ${filter === f ? "btn-primary" : ""}`}
                        onClick={() => setFilter(f)}
                    >
                        {f}
                    </button>
                ))}
            </div>
            {blocking.length > 0 && (
                <div
                    className="px-4 py-3 border-b border-[var(--status-critical)] bg-[var(--status-critical)]/10 flex items-center gap-3 flex-wrap"
                    data-testid="clock-paused-banner"
                >
                    <span className="badge t-crit">⛔ CLOCK FROZEN</span>
                    <span className="text-sm">
                        {blocking.length} grounded aircraft awaiting a decision — reassign a real tail via
                        Aircraft Control, or cancel the rotation below. The whole operation is on hold until
                        this is resolved.
                    </span>
                    <button className="btn btn-primary ml-auto" onClick={onOpenAircraftControl}>
                        ▸ OPEN AIRCRAFT CONTROL
                    </button>
                </div>
            )}
            <div className="flex-1 scroll-area">
                {incs.length === 0 && (
                    <div className="p-6 t-muted font-mono-jb text-xs" data-testid="no-incidents">
                        [SYS] No {filter.toLowerCase()} incidents. Advance the clock to spawn disruptions.
                    </div>
                )}
                {incs.map((i) => (
                    <IncidentCard
                        key={i.id}
                        inc={i}
                        state={state}
                        onResolve={onResolve}
                        onAskAdvisor={onAskAdvisor}
                        onOpenAircraftControl={onOpenAircraftControl}
                    />
                ))}
            </div>
        </div>
    );
}

const VERDICT_TONE = { OPTIMAL: "t-nominal", GOOD: "t-info", SUBOPTIMAL: "t-warn" };

function DecisionGrade({ grade }) {
    if (!grade) return null;
    return (
        <div className="mt-2 border border-white/10 px-3 py-2 font-mono-jb text-xs" data-testid="decision-grade">
            <div className={`uppercase-wide ${VERDICT_TONE[grade.verdict] || "t-sec"}`}>
                DECISION GRADE: {grade.verdict}
            </div>
            <div className="t-sec mt-1">
                YOU CHOSE {grade.player_choice === "cancel" ? "CANCEL" : grade.player_choice} · total impact $
                {grade.player_impact_usd?.toLocaleString()}
            </div>
            <div className="t-muted mt-0.5">
                BEST AVAILABLE: {grade.best_choice === "cancel" ? "CANCEL" : grade.best_choice} · $
                {grade.best_impact_usd?.toLocaleString()}
                {grade.delta_usd > 0 && ` (you cost $${grade.delta_usd.toLocaleString()} more)`}
            </div>
        </div>
    );
}

function IncidentCard({ inc, state, onResolve, onAskAdvisor, onOpenAircraftControl }) {
    const [picking, setPicking] = useState(false);
    const tone =
        inc.severity === "major"
            ? "border-l-[var(--status-critical)]"
            : "border-l-[var(--status-info)]";
    const flight = state.flights.find((f) => f.id === inc.flight_id);
    const toEscalation = minutesToEscalation(inc, state);
    return (
        <div className={`border-b border-white/[0.06] border-l-4 ${tone} px-4 py-3`} data-testid={`incident-${inc.id}`}>
            <div className="flex items-center gap-3 flex-wrap">
                <span className="badge t-info">{inc.id}</span>
                <span className="font-azeret t-info">{KIND_LABEL[inc.type] || inc.type}</span>
                <span className={`badge ${inc.severity === "major" ? "t-crit" : "t-sec"}`}>
                    {inc.severity.toUpperCase()}
                </span>
                {inc.escalated && (
                    <span className="badge t-crit" data-testid={`incident-escalated-${inc.id}`} title={inc.escalation_note}>
                        ESCALATED
                    </span>
                )}
                {inc.delay_code && (
                    <span className="badge t-muted" title="IATA standard delay code">
                        DLY {inc.delay_code}
                    </span>
                )}
                <span className="uppercase-wide t-sec">
                    {inc.flight_callsign} {flight ? `${flight.origin}→${flight.destination}` : ""}
                </span>
                <span className="uppercase-wide t-muted ml-auto">
                    {inc.reported_by ? `${inc.reported_by} · ` : ""}RAISED {inc.raised_at?.slice(11, 16)}Z
                </span>
                {toEscalation !== null && (
                    <span
                        className={`badge ${
                            toEscalation <= 10 ? "t-crit" : toEscalation <= 30 ? "t-warn" : "t-muted"
                        }`}
                        data-testid={`incident-fuse-${inc.id}`}
                        title={`Left unattended this escalates to MAJOR and adds ${
                            state.config?.escalation_extra_delay_min ?? 30
                        }min of delay.`}
                    >
                        ⏱ ESCALATES IN {toEscalation}M
                    </span>
                )}
                <span
                    className={`badge ${inc.status === "open" ? "t-warn" : "t-nominal"}`}
                    data-testid={`incident-status-${inc.id}`}
                >
                    {inc.status.toUpperCase()}
                </span>
            </div>
            <div className="mt-2 text-sm">{inc.description}</div>
            {inc.escalation_note && (
                <div className="mt-1 font-mono-jb text-xs t-crit">{inc.escalation_note}</div>
            )}
            {inc.affected_crew_name && (
                <div className="mt-1 font-mono-jb text-xs t-crit">
                    AFFECTED: {inc.affected_crew_id} {inc.affected_crew_name}
                </div>
            )}
            {inc.replacement_crew_name && (
                <div className="mt-1 font-mono-jb text-xs t-nominal">
                    REPLACED BY: {inc.replacement_crew_id} {inc.replacement_crew_name}
                </div>
            )}
            {inc.resolution && (
                <div className="mt-1 font-mono-jb text-xs t-nominal">
                    RESOLVED VIA: {inc.resolution_label}
                </div>
            )}
            {inc.resolution_note && (
                <div className="mt-1 font-mono-jb text-xs t-warn">{inc.resolution_note}</div>
            )}
            {inc.decision_grade && <DecisionGrade grade={inc.decision_grade} />}
            {inc.status === "open" && inc.requires_aircraft_decision && (
                <div className="mt-2 font-mono-jb text-xs t-crit" data-testid={`aircraft-decision-hint-${inc.id}`}>
                    ⛔ GROUNDED — not MEL-deferrable. Reassign a real tail via AIRCRAFT CONTROL, or cancel below.
                    The whole clock is frozen until this is resolved.
                </div>
            )}
            {inc.status === "open" && (
                <div className="mt-3 flex flex-wrap gap-2 items-center">
                    {inc.requires_aircraft_decision && (
                        <button
                            data-testid={`inc-open-ac-${inc.id}`}
                            className="btn btn-primary"
                            onClick={onOpenAircraftControl}
                        >
                            ▸ AIRCRAFT CONTROL
                        </button>
                    )}
                    {!picking && (
                        <>
                            <button
                                data-testid={`inc-pick-${inc.id}`}
                                className="btn btn-primary"
                                onClick={() => setPicking(true)}
                            >
                                ▸ DECIDE
                            </button>
                            <button
                                data-testid={`inc-advisor-${inc.id}`}
                                className="btn"
                                onClick={() => onAskAdvisor(inc.id)}
                            >
                                ASK ADVISOR
                            </button>
                        </>
                    )}
                    {picking &&
                        inc.options.map((opt) => {
                            const infeasible = opt.feasible === false;
                            return (
                                <button
                                    key={opt.action}
                                    data-testid={`inc-act-${inc.id}-${opt.action}`}
                                    className={`btn ${infeasible ? "opacity-40 cursor-not-allowed" : opt.action === "cancel" ? "btn-danger" : opt.action === "delay" ? "btn-warn" : "btn-primary"}`}
                                    disabled={infeasible}
                                    onClick={() => {
                                        setPicking(false);
                                        onResolve(inc.id, opt.action);
                                    }}
                                    title={infeasible ? opt.reason : `Cost $${opt.cost_usd.toLocaleString()}, OTP hit ${opt.otp_hit ?? 0}`}
                                >
                                    {opt.label}
                                    {opt.detail && !infeasible && (
                                        <span className="t-info ml-2">{opt.detail}</span>
                                    )}
                                    <span className="t-muted ml-2">${opt.cost_usd.toLocaleString()}</span>
                                </button>
                            );
                        })}
                    {picking &&
                        inc.options
                            .filter((o) => o.feasible === false)
                            .map((o) => (
                                <div
                                    key={`${o.action}-reason`}
                                    className="w-full font-mono-jb text-[10px] t-muted"
                                    data-testid={`inc-infeasible-${inc.id}-${o.action}`}
                                >
                                    ✕ {o.label}: {o.reason}
                                </div>
                            ))}
                    {picking && (
                        <button className="btn" onClick={() => setPicking(false)} data-testid={`inc-cancel-${inc.id}`}>
                            CANCEL
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
