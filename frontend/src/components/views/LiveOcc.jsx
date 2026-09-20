import React, { useEffect, useState } from "react";
import { api } from "../../api";

const SEVERITY_TONE = {
    major: "t-crit",
    minor: "t-warn",
};

function flightTone(flight) {
    if (flight.status === "cancelled" || flight.status === "diverted") return "border-[var(--status-critical)] bg-[var(--status-critical)]/15";
    if (flight.aog_hold || flight.delay_min >= 60) return "border-[var(--status-critical)] bg-[var(--status-critical)]/10";
    if (flight.delay_min > 0 || flight.curfew_exposure !== "none") return "border-[var(--status-warning)] bg-[var(--status-warning)]/10";
    if (flight.status === "airborne") return "border-[var(--status-nominal)] bg-[var(--status-nominal)]/10";
    return "border-[var(--status-info)] bg-[var(--status-info)]/10";
}

function fmtEstimate(iso) {
    return iso ? `${iso.slice(11, 16)}Z` : "—";
}

function PriorityQueue({ items, selectedFlightId, onSelect }) {
    return (
        <section className="min-w-[230px] border-r border-white/10 flex flex-col" data-testid="occ-priority-queue">
            <div className="px-4 py-3 border-b border-white/10">
                <div className="label-key">PRIORITY QUEUE</div>
                <div className="font-azeret text-sm">TRIAGE BY CONSEQUENCE</div>
            </div>
            <div className="flex-1 overflow-y-auto">
                {!items.length && (
                    <div className="px-4 py-5 font-mono-jb text-xs t-nominal">[OK] NO OPEN DISRUPTIONS</div>
                )}
                {items.map((item) => (
                    <button
                        key={item.incident_id}
                        onClick={() => onSelect(item.flight_id)}
                        className={`w-full text-left px-4 py-3 border-b border-white/[0.06] hover:bg-white/[0.03] ${
                            selectedFlightId === item.flight_id ? "bg-white/[0.05] border-l-2 border-l-[var(--status-info)]" : ""
                        }`}
                        data-testid={`occ-priority-${item.incident_id}`}
                    >
                        <div className="flex items-center gap-2 font-mono-jb text-[10px]">
                            <span className="t-muted">P{item.priority}</span>
                            <span className={SEVERITY_TONE[item.severity] || "t-sec"}>{item.type}</span>
                            {item.requires_aircraft_decision && <span className="badge t-crit">AOG</span>}
                        </div>
                        <div className="font-azeret text-sm mt-1 t-info">{item.callsign}</div>
                        <div className="font-mono-jb text-[10px] t-sec mt-0.5">{item.route}</div>
                        <div className="font-mono-jb text-[10px] t-muted mt-1 line-clamp-2">{item.description}</div>
                        {!item.escalated && item.escalates_in_min !== null && (
                            <div className={`uppercase-wide mt-1 ${item.escalates_in_min <= 10 ? "t-crit" : "t-warn"}`}>
                                ESCALATES IN {item.escalates_in_min}M
                            </div>
                        )}
                    </button>
                ))}
            </div>
        </section>
    );
}

function Network({ rows, selectedFlightId, onSelect }) {
    return (
        <section className="min-w-[430px] flex-1 flex flex-col" data-testid="occ-network">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">NETWORK TIMELINE</div>
                    <div className="font-azeret text-sm">TAIL ROTATIONS · LIVE STATE</div>
                </div>
                <div className="font-mono-jb text-[10px] t-muted ml-auto">CLICK A SECTOR TO FOCUS</div>
            </div>
            <div className="flex-1 overflow-auto">
                {rows.map((tail) => (
                    <div key={tail.reg} className={`border-b border-white/[0.06] ${tail.grounded ? "bg-[var(--status-critical)]/[0.04]" : ""}`}>
                        <div className="px-4 py-2 flex items-center gap-2 font-mono-jb text-xs border-b border-white/[0.04]">
                            <span className={tail.grounded ? "t-crit" : "t-info"}>{tail.reg}</span>
                            <span className="t-muted">{tail.type}</span>
                            {tail.spare && <span className="badge t-nominal">SPARE</span>}
                            {tail.grounded && (
                                <span className="badge t-crit" title="This tail cannot operate until Maintenance releases it">
                                    AOG · EST {fmtEstimate(tail.maintenance_estimate)}
                                </span>
                            )}
                        </div>
                        <div className="flex flex-wrap gap-1.5 px-4 py-2">
                            {!tail.flights.length && <span className="font-mono-jb text-[10px] t-muted">NO PROGRAMME · AVAILABLE AS RESERVE</span>}
                            {tail.flights.map((flight) => (
                                <button
                                    key={flight.id}
                                    onClick={() => onSelect(flight.id)}
                                    className={`min-w-[126px] text-left border-l-2 px-2 py-1.5 font-mono-jb text-[10px] hover:bg-white/[0.06] ${flightTone(flight)} ${
                                        selectedFlightId === flight.id ? "outline outline-1 outline-[var(--status-info)]" : ""
                                    }`}
                                    data-testid={`occ-flight-${flight.callsign}`}
                                >
                                    <div className="flex justify-between gap-2">
                                        <span className="t-info">{flight.callsign}</span>
                                        {flight.delay_min > 0 && <span className="t-warn">+{flight.delay_min}</span>}
                                    </div>
                                    <div className="t-sec">{flight.route}</div>
                                    <div className="t-muted">{flight.scheduled_departure} → {flight.estimated_arrival}</div>
                                    {flight.aog_hold && <div className="t-crit uppercase-wide">WAITING AOG</div>}
                                    {flight.curfew_exposure !== "none" && (
                                        <div className={flight.curfew_exposure === "confirmed" ? "t-crit uppercase-wide" : "t-warn uppercase-wide"}>
                                            CURFEW {flight.curfew_exposure.toUpperCase()}
                                        </div>
                                    )}
                                </button>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}

function FlightWorkspace({ selected, onOpenIncidents, onOpenAircraft }) {
    if (!selected) {
        return (
            <section className="min-w-[280px] border-l border-white/10 px-4 py-5" data-testid="occ-flight-workspace">
                <div className="label-key">FLIGHT WORKSPACE</div>
                <div className="font-mono-jb text-xs t-muted mt-2">SELECT A SECTOR OR QUEUE ITEM.</div>
            </section>
        );
    }
    const { flight, aircraft, crew, incidents, downstream, impact } = selected;
    return (
        <section className="min-w-[280px] border-l border-white/10 flex flex-col" data-testid="occ-flight-workspace">
            <div className="px-4 py-3 border-b border-white/10">
                <div className="label-key">FLIGHT WORKSPACE</div>
                <div className="font-azeret text-lg t-info">{flight.callsign}</div>
                <div className="font-mono-jb text-xs t-sec">{flight.route} · STD {flight.scheduled_departure}</div>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
                <div className="font-mono-jb text-xs">
                    <div className="label-key">OPERATING STATUS</div>
                    <div className="mt-1 t-sec">{flight.status.toUpperCase()} · EST DEP {flight.estimated_departure} · EST ARR {flight.estimated_arrival}</div>
                    {flight.delay_min > 0 && <div className="t-warn mt-1">DELAY +{flight.delay_min}M · REACTIONARY {impact.reactionary_delay_min}M</div>}
                    {impact.curfew_exposure !== "none" && (
                        <div className={impact.curfew_exposure === "confirmed" ? "t-crit mt-1" : "t-warn mt-1"}>
                            LHR CURFEW {impact.curfew_exposure.toUpperCase()}
                        </div>
                    )}
                </div>

                <div className="font-mono-jb text-xs">
                    <div className="label-key">AIRCRAFT</div>
                    <div className={aircraft.grounded ? "t-crit mt-1" : "t-sec mt-1"}>
                        {aircraft.reg} · {aircraft.type} {aircraft.grounded ? `· AOG EST ${fmtEstimate(aircraft.maintenance_estimate)}` : "· SERVICEABLE"}
                    </div>
                    {aircraft.grounded && (
                        <button className="btn btn-primary mt-2" onClick={onOpenAircraft}>
                            ▸ AIRCRAFT CONTROL
                        </button>
                    )}
                </div>

                <div className="font-mono-jb text-xs">
                    <div className="label-key">CREW · DUTY HEADROOM</div>
                    {!crew.length && <div className="t-warn mt-1">UNCREWED SECTOR</div>}
                    {crew.map((member) => (
                        <div key={member.id} className="mt-1 flex gap-2">
                            <span className="t-info">{member.rank} {member.id}</span>
                            <span className="t-sec truncate">{member.name}</span>
                            {member.duty_slack_min !== null && (
                                <span className={member.duty_slack_min < 0 ? "t-crit ml-auto" : member.duty_slack_min < 60 ? "t-warn ml-auto" : "t-muted ml-auto"}>
                                    {member.duty_slack_min}M
                                </span>
                            )}
                        </div>
                    ))}
                </div>

                <div className="font-mono-jb text-xs">
                    <div className="label-key">DOWNSTREAM IMPACT</div>
                    <div className="t-warn mt-1">{impact.downstream_sectors} SECTORS · {impact.downstream_delay_min}M CURRENTLY EXPOSED</div>
                    {downstream.length === 0 && <div className="t-nominal mt-1">[OK] NO FURTHER ACTIVE SECTORS</div>}
                    {downstream.map((next) => (
                        <div key={next.id} className="mt-1 flex gap-2 t-sec">
                            <span className="t-info">{next.callsign}</span>
                            <span>{next.route}</span>
                            {next.delay_min > 0 && <span className="t-warn ml-auto">+{next.delay_min}M</span>}
                        </div>
                    ))}
                </div>

                {incidents.length > 0 && (
                    <div className="font-mono-jb text-xs">
                        <div className="label-key">LIVE EXCEPTIONS</div>
                        {incidents.map((incident) => (
                            <div key={incident.id} className="mt-1 t-crit">{incident.type} · {incident.description}</div>
                        ))}
                        <button className="btn btn-primary mt-2" onClick={onOpenIncidents}>
                            ▸ OPEN INCIDENT QUEUE
                        </button>
                    </div>
                )}
            </div>
        </section>
    );
}

export default function LiveOcc({ state, onOpenIncidents, onOpenAircraft }) {
    const [focusFlightId, setFocusFlightId] = useState(null);
    const [workspace, setWorkspace] = useState(null);
    const [error, setError] = useState(false);

    useEffect(() => {
        let cancelled = false;
        setError(false);
        api.occWorkspace(state.id, focusFlightId)
            .then((next) => {
                if (!cancelled) setWorkspace(next);
            })
            .catch(() => {
                if (!cancelled) setError(true);
            });
        return () => {
            cancelled = true;
        };
    }, [state, focusFlightId]);

    if (error) {
        return <div className="p-6 font-mono-jb text-xs t-crit">[SYS] LIVE OCC FEED UNAVAILABLE — RETRY AFTER BACKEND RECOVERS.</div>;
    }
    if (!workspace) {
        return <div className="p-6 font-mono-jb text-xs t-muted">[WAIT] BUILDING COMMON OPERATING PICTURE…</div>;
    }

    const selectedFlightId = workspace.selected?.flight?.id;
    return (
        <div className="h-full min-w-[980px] flex flex-col" data-testid="live-occ">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">LIVE OCC</div>
                    <div className="font-azeret text-lg">COMMON OPERATING PICTURE</div>
                </div>
                <div className="font-mono-jb text-[10px] t-muted ml-auto">
                    CLOCK RUNNING · AOG HOLDS AFFECTED ROTATIONS ONLY
                </div>
            </div>
            <div className="flex-1 min-h-0 flex overflow-hidden">
                <PriorityQueue
                    items={workspace.priority_queue}
                    selectedFlightId={selectedFlightId}
                    onSelect={setFocusFlightId}
                />
                <Network rows={workspace.network} selectedFlightId={selectedFlightId} onSelect={setFocusFlightId} />
                <FlightWorkspace selected={workspace.selected} onOpenIncidents={onOpenIncidents} onOpenAircraft={onOpenAircraft} />
            </div>
        </div>
    );
}
