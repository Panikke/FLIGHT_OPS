import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import WarningBlock from "../WarningBlock";

const RANKS = ["CP", "FO", "SC", "CC"];
const statusOrder = { available: 0, standby: 1, on_duty: 2, off: 3, rest: 4, sick: 5 };

function clock(value) {
    return value ? value.slice(11, 16) : "--:--";
}

function pairingRows(state) {
    const groups = new Map();
    state.flights.forEach((flight) => {
        const id = flight.pairing_id || flight.id;
        if (!groups.has(id)) groups.set(id, []);
        groups.get(id).push(flight);
    });
    return [...groups.entries()].map(([id, flights]) => {
        const sorted = [...flights].sort((a, b) => a.std.localeCompare(b.std));
        const primary = sorted[0];
        const crewIds = [...new Set(sorted.flatMap((flight) => flight.assigned_crew_ids))];
        const required = primary.required_crew;
        const requiredCount = RANKS.reduce((total, rank) => total + (required[rank] || 0), 0);
        return { id, flights: sorted, primary, crewIds, required, requiredCount };
    }).sort((a, b) => a.primary.std.localeCompare(b.primary.std));
}

export default function FlightAssignmentDesk({ state, onChanged, onStartDay }) {
    const flights = state.flights;
    const pairings = useMemo(() => pairingRows({ flights }), [flights]);
    const [selectedPairingId, setSelectedPairingId] = useState(null);
    const [rank, setRank] = useState("CP");
    const [selectedCrewId, setSelectedCrewId] = useState(null);
    const [warnings, setWarnings] = useState([]);
    const [discretion, setDiscretion] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const selectedPairing = pairings.find((pairing) => pairing.id === selectedPairingId)
        || pairings.find((pairing) => pairing.crewIds.length < pairing.requiredCount)
        || pairings[0];

    const assigned = useMemo(() => {
        if (!selectedPairing) return [];
        return selectedPairing.crewIds.map((id) => state.crew.find((crew) => crew.id === id)).filter(Boolean);
    }, [selectedPairing, state.crew]);

    const assignedByRank = useMemo(() => RANKS.reduce((result, role) => {
        result[role] = assigned.filter((crew) => crew.rank === role);
        return result;
    }, {}), [assigned]);

    useEffect(() => {
        if (!selectedPairing) return;
        const nextGap = RANKS.find((role) => (assignedByRank[role]?.length || 0) < (selectedPairing.required[role] || 0));
        setRank(nextGap || "CP");
        setSelectedCrewId(null);
        setWarnings([]);
        setDiscretion(null);
        setError(null);
    }, [selectedPairing, assignedByRank]);

    const candidates = useMemo(() => {
        if (!selectedPairing) return [];
        const typeQual = selectedPairing.primary.required_crew.type_qual;
        return state.crew
            .filter((crew) => crew.rank === rank && !selectedPairing.crewIds.includes(crew.id))
            .sort((a, b) => {
                const qualification = Number(b.qualifications.includes(typeQual)) - Number(a.qualifications.includes(typeQual));
                if (qualification) return qualification;
                return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
            });
    }, [state.crew, selectedPairing, rank]);

    const selectedCrew = state.crew.find((crew) => crew.id === selectedCrewId);
    const hasCritical = warnings.some((warning) => warning.severity === "critical");

    async function inspectCrew(crewId) {
        if (!selectedPairing) return;
        setSelectedCrewId(crewId);
        setWarnings([]);
        setDiscretion(null);
        setError(null);
        try {
            const result = await api.precheck(state.id, selectedPairing.primary.id, crewId);
            setWarnings(result.warnings || []);
            setDiscretion(result.discretion || null);
        } catch {
            setError("Could not complete the legality pre-check. Try again before assigning.");
        }
    }

    async function assign(force = false, useDiscretion = false) {
        if (!selectedPairing || !selectedCrewId) return;
        setBusy(true);
        setError(null);
        try {
            const result = await api.assign(state.id, selectedPairing.primary.id, selectedCrewId, force, useDiscretion);
            if (!result.applied) {
                setWarnings(result.warnings || []);
                return;
            }
            setSelectedCrewId(null);
            await onChanged();
        } catch (err) {
            setError(err?.response?.data?.detail || "Assignment could not be saved.");
        } finally {
            setBusy(false);
        }
    }

    async function unassign(crewId) {
        if (!selectedPairing) return;
        setBusy(true);
        try {
            await api.unassign(state.id, selectedPairing.primary.id, crewId);
            await onChanged();
        } finally {
            setBusy(false);
        }
    }

    const completePairings = pairings.filter((pairing) => pairing.crewIds.length >= pairing.requiredCount).length;
    const allComplete = completePairings === pairings.length;

    if (!selectedPairing) {
        return <div className="p-5 font-mono-jb t-muted">No released flights are available for assignment.</div>;
    }

    return (
        <div className="h-full flex flex-col" data-testid="flight-assignment-desk">
            <header className="px-5 py-3 border-b border-white/10 flex items-center gap-4">
                <div>
                    <div className="label-key">PLANNER MODE · FLIGHT ASSIGNMENT</div>
                    <div className="font-azeret text-lg">PAIRING DESK</div>
                    <div className="font-mono-jb text-xs t-sec mt-1">Crew a whole rotation. Every selection is checked for qualification, status, rest and FTL before release.</div>
                </div>
                <div className="flex-1" />
                <div className="font-mono-jb text-xs uppercase-wide t-sec">PAIRINGS READY <span className="t-nominal">{completePairings}</span>/{pairings.length}</div>
                {state.phase === "ROSTER" && (
                    <button className={`btn ${allComplete ? "btn-ok" : "btn-warn"}`} onClick={onStartDay}>
                        {allComplete ? "▶ START DAY" : "▶ START DAY (GAPS REMAIN)"}
                    </button>
                )}
            </header>

            <div className="flex flex-1 overflow-hidden">
                <aside className="w-[280px] border-r border-white/10 flex flex-col">
                    <div className="px-4 py-3 border-b border-white/10 label-key">TODAY'S ROTATIONS</div>
                    <div className="scroll-area">
                        {pairings.map((pairing) => {
                            const active = pairing.id === selectedPairing.id;
                            const covered = pairing.crewIds.length >= pairing.requiredCount;
                            return (
                                <button key={pairing.id} data-testid={`pairing-${pairing.id}`} onClick={() => setSelectedPairingId(pairing.id)} className={`w-full text-left px-4 py-3 border-b border-white/[.06] ${active ? "bg-[var(--status-info)]/10 border-l-2 border-l-[var(--status-info)]" : "hover:bg-white/[.035]"}`}>
                                    <div className="flex justify-between font-mono-jb text-xs"><span className="t-info">{clock(pairing.primary.std)}Z · {pairing.primary.aircraft_reg}</span><span className={covered ? "t-nominal" : "t-warn"}>{covered ? "READY" : "GAP"}</span></div>
                                    <div className="font-azeret text-sm mt-1">{pairing.flights.map((flight) => `${flight.origin}–${flight.destination}`).join(" · ")}</div>
                                    <div className="font-mono-jb text-[11px] t-sec mt-1">{pairing.flights.map((flight) => flight.callsign).join(" / ")} · {pairing.crewIds.length}/{pairing.requiredCount} crew</div>
                                </button>
                            );
                        })}
                    </div>
                </aside>

                <main className="flex-1 min-w-[420px] flex flex-col border-r border-white/10">
                    <div className="px-5 py-4 border-b border-white/10">
                        <div className="label-key">SELECTED PAIRING · SAME CREW OPERATES ALL SECTORS</div>
                        <div className="font-azeret text-xl mt-1">{selectedPairing.flights.map((flight) => `${flight.callsign} ${flight.origin} → ${flight.destination}`).join("  ·  ")}</div>
                        <div className="font-mono-jb text-xs t-sec mt-2">{selectedPairing.primary.aircraft_type} {selectedPairing.primary.aircraft_reg} · STD {clock(selectedPairing.primary.std)}Z · {selectedPairing.flights.length} sector{selectedPairing.flights.length === 1 ? "" : "s"}</div>
                    </div>
                    <div className="p-5 border-b border-white/10">
                        <div className="label-key mb-3">CREW COVERAGE · CLICK A ROLE TO FILL ITS NEXT SLOT</div>
                        <div className="grid grid-cols-2 gap-3">
                            {RANKS.map((role) => {
                                const required = selectedPairing.required[role] || 0;
                                const crew = assignedByRank[role] || [];
                                const open = Math.max(0, required - crew.length);
                                return (
                                    <button key={role} disabled={!required} onClick={() => setRank(role)} className={`text-left panel-flush p-3 border ${rank === role ? "border-[var(--status-info)] bg-[var(--status-info)]/10" : "border-white/10"}`}>
                                        <div className="flex justify-between font-mono-jb text-xs"><span className="t-info">{role}</span><span className={open ? "t-warn" : "t-nominal"}>{crew.length}/{required}</span></div>
                                        <div className="font-mono-jb text-[11px] t-sec mt-2">{crew.length ? crew.map((member) => `${member.id} ${member.name}`).join(" · ") : "UNASSIGNED"}</div>
                                        {open > 0 && <div className="uppercase-wide t-warn mt-2">{open} SLOT{open === 1 ? "" : "S"} OPEN</div>}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                    <div className="flex-1 min-h-0 flex flex-col">
                        <div className="px-5 py-3 border-b border-white/10 flex justify-between"><div className="label-key">CANDIDATE BANK · {rank}</div><div className="uppercase-wide t-sec">{candidates.length} AVAILABLE TO REVIEW</div></div>
                        <div className="flex-1 scroll-area">
                            {candidates.map((crew) => {
                                const qualified = crew.qualifications.includes(selectedPairing.primary.required_crew.type_qual);
                                const selected = crew.id === selectedCrewId;
                                return <button key={crew.id} data-testid={`pairing-candidate-${crew.id}`} onClick={() => inspectCrew(crew.id)} className={`w-full text-left px-5 py-3 border-b border-white/[.05] flex gap-3 ${selected ? "bg-[var(--status-info)]/15" : "hover:bg-white/[.035]"}`}>
                                    <span className="font-mono-jb t-info text-xs w-16">{crew.id}</span><span className="font-mono-jb text-xs flex-1">{crew.name}</span><span className={qualified ? "t-nominal" : "t-crit"}>{qualified ? "TYPE QUAL" : "NO TYPE QUAL"}</span><span className={crew.status === "available" ? "t-nominal" : "t-warn"}>{crew.status.toUpperCase()}</span><span className="t-sec">REST {Math.round(crew.rest_hr_since_duty)}H · FAT {crew.fatigue_score}</span>
                                </button>;
                            })}
                            {!candidates.length && <div className="p-5 font-mono-jb text-xs t-warn">No unassigned {rank} candidates remain for this rotation.</div>}
                        </div>
                    </div>
                </main>

                <aside className="w-[340px] flex flex-col">
                    <div className="px-4 py-3 border-b border-white/10"><div className="label-key">LEGALITY GATE</div><div className="font-mono-jb text-xs t-sec mt-1">{selectedCrew ? `${selectedCrew.id} · ${selectedCrew.name}` : "Select a candidate to inspect."}</div></div>
                    <div className="flex-1 scroll-area p-4">
                        {selectedCrewId && !warnings.length && !error && <div className="font-mono-jb text-xs t-nominal">[OK] No legality issues detected. Cleared to assign to every sector in this pairing.</div>}
                        {!selectedCrewId && <div className="font-mono-jb text-xs t-muted">The gate prevents a crew member being assigned without a live check. This preserves the operating constraints used by the simulation.</div>}
                        {warnings.map((warning, index) => <WarningBlock key={`${warning.code || "warning"}-${index}`} warning={warning} testIdPrefix="pairing-warning" />)}
                        {error && <div className="font-mono-jb text-xs t-crit">ERR: {error}</div>}
                    </div>
                    <div className="border-t border-white/10 p-4 space-y-2">
                        <button data-testid="pairing-assign-btn" className="btn btn-primary w-full" disabled={!selectedCrewId || busy || hasCritical} onClick={() => assign()}>{busy ? "SAVING..." : `ASSIGN ${rank} TO PAIRING`}</button>
                        {hasCritical && discretion?.available && <button className="btn btn-warn w-full" disabled={busy} onClick={() => assign(false, true)}>COMMANDER'S DISCRETION +{discretion.overrun_min}M</button>}
                        {hasCritical && <button className="btn btn-danger w-full" disabled={busy} onClick={() => assign(true)}>OVERRIDE (BOOKS BREACH)</button>}
                        <div className="pt-2 border-t border-white/10"><div className="label-key mb-2">REMOVE FROM THIS PAIRING</div>{assigned.map((crew) => <div key={crew.id} className="flex justify-between items-center font-mono-jb text-xs py-1"><span>{crew.id} · {crew.rank}</span><button className="btn btn-danger !py-1 !px-2" disabled={busy} onClick={() => unassign(crew.id)}>REMOVE</button></div>)}{!assigned.length && <div className="font-mono-jb text-xs t-muted">No crew currently assigned.</div>}</div>
                    </div>
                </aside>
            </div>
        </div>
    );
}
