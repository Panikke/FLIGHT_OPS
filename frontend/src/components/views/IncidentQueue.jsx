import React, { useState } from "react";

const KIND_LABEL = {
    CREW_SICK: "CREW SICKNESS",
    LATE_REPORT: "LATE REPORT",
    WEATHER: "WX DISRUPT",
    TECH: "TECH / MEL",
    ATC_FLOW: "ATC FLOW",
};

export default function IncidentQueue({ state, onResolve, onAskAdvisor }) {
    const [filter, setFilter] = useState("OPEN");
    const incs = state.incidents.filter((i) =>
        filter === "OPEN" ? i.status === "open" : filter === "ALL" ? true : i.status === "resolved"
    );

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
                    />
                ))}
            </div>
        </div>
    );
}

function IncidentCard({ inc, state, onResolve, onAskAdvisor }) {
    const [picking, setPicking] = useState(false);
    const tone = inc.severity === "major" ? "border-l-[var(--status-critical)]" : "border-l-[var(--status-warning)]";
    const flight = state.flights.find((f) => f.id === inc.flight_id);
    return (
        <div className={`border-b border-white/[0.06] border-l-4 ${tone} px-4 py-3`} data-testid={`incident-${inc.id}`}>
            <div className="flex items-center gap-3">
                <span className="badge t-info">{inc.id}</span>
                <span className="font-azeret t-info">{KIND_LABEL[inc.type] || inc.type}</span>
                <span className={`badge ${inc.severity === "major" ? "t-crit" : "t-warn"}`}>
                    {inc.severity.toUpperCase()}
                </span>
                <span className="uppercase-wide t-sec">
                    {inc.flight_callsign} {flight ? `${flight.origin}→${flight.destination}` : ""}
                </span>
                <span className="uppercase-wide t-muted ml-auto">RAISED {inc.raised_at?.slice(11, 16)}Z</span>
                <span
                    className={`badge ${inc.status === "open" ? "t-warn" : "t-nominal"}`}
                    data-testid={`incident-status-${inc.id}`}
                >
                    {inc.status.toUpperCase()}
                </span>
            </div>
            <div className="mt-2 text-sm">{inc.description}</div>
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
            {inc.status === "open" && (
                <div className="mt-3 flex flex-wrap gap-2 items-center">
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
                        inc.options.map((opt) => (
                            <button
                                key={opt.action}
                                data-testid={`inc-act-${inc.id}-${opt.action}`}
                                className={`btn ${opt.action === "cancel" ? "btn-danger" : opt.action === "delay" ? "btn-warn" : "btn-primary"}`}
                                onClick={() => {
                                    setPicking(false);
                                    onResolve(inc.id, opt.action);
                                }}
                                title={`Cost $${opt.cost_usd}, OTP hit ${opt.otp_hit ?? 0}`}
                            >
                                {opt.label} <span className="t-muted ml-2">${opt.cost_usd}</span>
                            </button>
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
