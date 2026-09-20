import React, { useEffect, useState } from "react";
import { api } from "../../api";
import { ReassignModal } from "./AircraftControl";

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

function DisruptionFocusDesk({ state, selected, onRecovered }) {
    const [control, setControl] = useState(null);
    const [reassign, setReassign] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;
        api.aircraftControl(state.id)
            .then((next) => {
                if (!cancelled) {
                    setControl(next);
                    setError(null);
                }
            })
            .catch(() => !cancelled && setError("Recovery feed unavailable."));
        return () => { cancelled = true; };
    }, [state.id, state.clock, state.incidents]);

    if (!selected) {
        return <div className="p-6 font-mono-jb text-xs t-muted">[WAIT] ISOLATING AFFECTED ROTATION…</div>;
    }

    const { flight, aircraft, crew, downstream, impact, incidents } = selected;
    const rotation = control?.rotations?.find((r) => r.callsigns?.includes(flight.callsign));
    const spares = (control?.fleet || []).filter((ac) => ac.spare && !ac.grounded && !ac.in_c_check);

    return (
        <div className="h-full overflow-auto bg-[#050505]" data-testid="occ-focus-desk">
            <header className="px-6 py-4 border-b-2 border-[var(--status-critical)] bg-[var(--status-critical)]/[0.07] flex items-start gap-4">
                <div className="w-2 self-stretch bg-[var(--status-critical)] shadow-[0_0_18px_var(--status-critical)]" />
                <div>
                    <div className="label-key t-crit">AOG RECOVERY DESK · NETWORK SUPPRESSED</div>
                    <h2 className="font-azeret text-2xl mt-1">{aircraft.reg} / {flight.callsign}</h2>
                    <p className="font-mono-jb text-xs t-sec mt-1">
                        {flight.route} · {aircraft.type} · ESTIMATE {fmtEstimate(aircraft.maintenance_estimate)} · {impact.downstream_sectors} SECTORS AT RISK
                    </p>
                </div>
                <div className="ml-auto text-right font-mono-jb text-[10px] t-warn">
                    CLOCK CONTINUES<br />ONLY THIS ROTATION IS HELD
                </div>
            </header>

            <div className="grid grid-cols-[minmax(0,1fr)_320px] gap-0 min-h-[calc(100%-86px)]">
                <main className="p-6 border-r border-white/10 space-y-6">
                    <section>
                        <div className="label-key">DECISION CONTEXT</div>
                        {incidents.map((incident) => (
                            <div key={incident.id} className="mt-2 border-l-2 border-[var(--status-critical)] bg-white/[0.03] px-4 py-3 font-mono-jb text-xs t-sec">
                                <span className="t-crit">{incident.type}</span> · {incident.description}
                            </div>
                        ))}
                    </section>

                    <section>
                        <div className="label-key">AFFECTED TAIL ROTATION</div>
                        <div className="mt-2 grid gap-2">
                            {[flight, ...downstream].map((sector, index) => (
                                <div key={sector.id} className={`grid grid-cols-[28px_92px_1fr_auto] gap-3 items-center border px-3 py-3 font-mono-jb text-xs ${index === 0 ? "border-[var(--status-critical)] bg-[var(--status-critical)]/[0.08]" : "border-white/10"}`}>
                                    <span className={index === 0 ? "t-crit" : "t-muted"}>{String(index + 1).padStart(2, "0")}</span>
                                    <span className="t-info">{sector.callsign}</span>
                                    <span className="t-sec">{sector.route}</span>
                                    <span className={sector.delay_min > 0 ? "t-warn" : "t-muted"}>{sector.delay_min > 0 ? `+${sector.delay_min}M` : "PENDING"}</span>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section>
                        <div className="label-key">OPERATING CREW · DUTY HEADROOM</div>
                        <div className="mt-2 grid grid-cols-2 gap-x-8 gap-y-2 font-mono-jb text-xs">
                            {crew.map((member) => (
                                <div key={member.id} className="flex gap-2 border-b border-white/[0.06] pb-2">
                                    <span className="t-info">{member.rank}</span>
                                    <span className="t-sec truncate">{member.name}</span>
                                    <span className={member.duty_slack_min < 60 ? "t-warn ml-auto" : "t-muted ml-auto"}>{member.duty_slack_min ?? "—"}M</span>
                                </div>
                            ))}
                        </div>
                    </section>
                </main>

                <aside className="p-5 space-y-5 bg-black/30">
                    <section>
                        <div className="label-key">AVAILABLE SPARE AIRCRAFT</div>
                        <div className="mt-2 space-y-2">
                            {!control && <div className="font-mono-jb text-xs t-muted">CHECKING FLEET POSITION…</div>}
                            {spares.map((ac) => (
                                <div key={ac.reg} className="border border-[var(--status-nominal)]/40 px-3 py-2 font-mono-jb text-xs">
                                    <div className="t-nominal">{ac.reg} · {ac.type}</div>
                                    <div className="t-muted mt-1">{ac.location || "LHR"} · RESERVE / SERVICEABLE</div>
                                </div>
                            ))}
                            {control && !spares.length && <div className="font-mono-jb text-xs t-warn">NO SERVICEABLE SPARES AT THIS TIME.</div>}
                        </div>
                    </section>

                    <section className="border-t border-white/10 pt-5">
                        <div className="label-key">RECOVERY ACTION</div>
                        <p className="font-mono-jb text-xs t-sec mt-2 leading-relaxed">
                            Test same-type spare, ferry and larger-aircraft cover. The recovery screen validates position, airport suitability, qualified crew, FTL and the commercial upgauge cost before dispatch.
                        </p>
                        {rotation ? (
                            <button className="btn btn-primary w-full mt-4" onClick={() => setReassign(rotation)} data-testid="focus-open-recovery">
                                ▸ PLAN TAIL RECOVERY
                            </button>
                        ) : (
                            <div className="font-mono-jb text-xs t-warn mt-3">{error || "LOCATING ACTIVE ROTATION…"}</div>
                        )}
                    </section>
                </aside>
            </div>

            {reassign && (
                <ReassignModal
                    state={state}
                    rotation={reassign}
                    fleet={control.fleet}
                    minTurn={control.min_turnaround_min}
                    hub={control.hub || "LHR"}
                    onClose={() => setReassign(null)}
                    onAssigned={async () => {
                        setReassign(null);
                        await onRecovered();
                    }}
                />
            )}
        </div>
    );
}

export default function LiveOcc({ state, onOpenIncidents, onOpenAircraft, onChanged }) {
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

    const criticalItem = workspace?.priority_queue?.find((item) => item.requires_aircraft_decision);
    const criticalFlightId = criticalItem?.flight_id;
    useEffect(() => {
        if (criticalFlightId && focusFlightId !== criticalFlightId) {
            setFocusFlightId(criticalFlightId);
        }
    }, [criticalFlightId, focusFlightId]);

    if (error) {
        return <div className="p-6 font-mono-jb text-xs t-crit">[SYS] LIVE OCC FEED UNAVAILABLE — RETRY AFTER BACKEND RECOVERS.</div>;
    }
    if (!workspace) {
        return <div className="p-6 font-mono-jb text-xs t-muted">[WAIT] BUILDING COMMON OPERATING PICTURE…</div>;
    }

    const selectedFlightId = workspace.selected?.flight?.id;
    if (criticalItem) {
        return (
            <DisruptionFocusDesk
                state={state}
                selected={workspace.selected}
                onRecovered={async () => {
                    await onChanged?.();
                    const next = await api.occWorkspace(state.id, criticalItem.flight_id);
                    setWorkspace(next);
                }}
            />
        );
    }
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
