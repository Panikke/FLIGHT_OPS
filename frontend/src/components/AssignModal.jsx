import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

export default function AssignModal({ state, flight, onClose, onAssigned }) {
    const [filter, setFilter] = useState("ALL");
    const [search, setSearch] = useState("");
    const [selected, setSelected] = useState(null);
    const [warnings, setWarnings] = useState([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    const candidates = useMemo(() => {
        const typeQ = flight.required_crew.type_qual;
        let list = state.crew.filter((c) => {
            if (filter !== "ALL" && c.rank !== filter) return false;
            if (search && !c.id.toLowerCase().includes(search.toLowerCase()) && !c.name.toLowerCase().includes(search.toLowerCase())) return false;
            return true;
        });
        // sort: qualified first, available first, standby next, rest sick last
        const statusOrder = { available: 0, standby: 1, on_duty: 2, off: 3, rest: 4, sick: 5 };
        list.sort((a, b) => {
            const qa = a.qualifications.includes(typeQ) ? 0 : 1;
            const qb = b.qualifications.includes(typeQ) ? 0 : 1;
            if (qa !== qb) return qa - qb;
            return (statusOrder[a.status] ?? 9) - (statusOrder[b.status] ?? 9);
        });
        return list.slice(0, 80);
    }, [state.crew, flight, filter, search]);

    useEffect(() => {
        if (!selected) {
            setWarnings([]);
            return;
        }
        let cancelled = false;
        api.precheck(state.id, flight.id, selected).then((d) => {
            if (!cancelled) setWarnings(d.warnings || []);
        }).catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [selected, flight.id, state.id]);

    const hasCritical = warnings.some((w) => w.severity === "critical");

    async function doAssign(force = false) {
        if (!selected) return;
        setBusy(true);
        setError(null);
        try {
            const res = await api.assign(state.id, flight.id, selected, force);
            if (!res.applied) {
                setWarnings(res.warnings);
                return;
            }
            onAssigned();
            setSelected(null);
        } catch (e) {
            setError(e?.response?.data?.detail || String(e));
        } finally {
            setBusy(false);
        }
    }

    async function doUnassign(cid) {
        setBusy(true);
        try {
            await api.unassign(state.id, flight.id, cid);
            onAssigned();
        } finally {
            setBusy(false);
        }
    }

    const assignedCrew = flight.assigned_crew_ids
        .map((cid) => state.crew.find((c) => c.id === cid))
        .filter(Boolean);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-md bg-black/80" data-testid="assign-modal">
            <div className="panel w-[1100px] max-w-[96vw] h-[85vh] flex flex-col" style={{ borderTop: "2px solid var(--status-info)" }}>
                <div className="px-5 py-3 border-b border-white/10 flex items-center gap-4">
                    <div>
                        <div className="label-key">CREW PAIRING</div>
                        <div className="font-azeret text-lg">
                            {flight.callsign} · {flight.origin} → {flight.destination} · {flight.aircraft_type} ({flight.aircraft_reg})
                        </div>
                        {(() => {
                            const sibs = state.flights.filter(
                                (f) => f.pairing_id && f.pairing_id === flight.pairing_id,
                            );
                            if (sibs.length > 1) {
                                return (
                                    <div className="uppercase-wide t-warn mt-1" data-testid="pairing-notice">
                                        OUT-AND-BACK PAIRING · {sibs.length} sectors · same crew operates the lot:
                                        {" "}
                                        {sibs.map((s) => `${s.callsign} ${s.origin}-${s.destination}`).join(" · ")}
                                    </div>
                                );
                            }
                            if (flight.block_min > 360) {
                                return (
                                    <div className="uppercase-wide t-warn mt-1" data-testid="pairing-notice">
                                        LONG-HAUL SECTOR · crew night-stops downroute, return next day
                                    </div>
                                );
                            }
                            return null;
                        })()}
                    </div>
                    <div className="uppercase-wide t-sec">
                        STD {flight.std.slice(11, 16)}Z · BLK {Math.floor(flight.block_min / 60)}h{(flight.block_min % 60).toString().padStart(2, "0")}
                    </div>
                    <div className="flex-1" />
                    <button data-testid="close-assign-modal" className="btn" onClick={onClose}>
                        CLOSE
                    </button>
                </div>

                <div className="flex flex-1 overflow-hidden">
                    {/* Left: crew picker */}
                    <div className="w-2/3 flex flex-col border-r border-white/10">
                        <div className="px-4 py-2 border-b border-white/10 flex gap-2 items-center">
                            <input
                                data-testid="crew-search"
                                placeholder="SEARCH ID / NAME"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                            />
                            {["ALL", "CP", "FO", "SC", "CC"].map((r) => (
                                <button
                                    key={r}
                                    data-testid={`rank-filter-${r}`}
                                    className={`btn ${filter === r ? "btn-primary" : ""}`}
                                    onClick={() => setFilter(r)}
                                >
                                    {r}
                                </button>
                            ))}
                        </div>
                        <div className="flex-1 scroll-area">
                            <table className="w-full text-xs font-mono-jb">
                                <thead className="sticky top-0 bg-[#0a0a0c]">
                                    <tr className="uppercase-wide t-muted">
                                        <th className="text-left px-3 py-2 border-b border-white/10">ID</th>
                                        <th className="text-left px-3 py-2 border-b border-white/10">NAME</th>
                                        <th className="text-left px-3 py-2 border-b border-white/10">RANK</th>
                                        <th className="text-left px-3 py-2 border-b border-white/10">QUAL</th>
                                        <th className="text-left px-3 py-2 border-b border-white/10">REST</th>
                                        <th className="text-left px-3 py-2 border-b border-white/10">FAT</th>
                                        <th className="text-left px-3 py-2 border-b border-white/10">STAT</th>
                                    </tr>
                                </thead>
                                <tbody className="zebra">
                                    {candidates.map((c) => {
                                        const typeQ = flight.required_crew.type_qual;
                                        const qual = c.qualifications.includes(typeQ);
                                        const isSel = selected === c.id;
                                        const statusTone = c.status === "available" ? "t-nominal" : c.status === "standby" ? "t-warn" : c.status === "sick" ? "t-crit" : "t-sec";
                                        return (
                                            <tr
                                                key={c.id}
                                                onClick={() => setSelected(c.id)}
                                                data-testid={`assign-crew-${c.id}`}
                                                className={`cursor-pointer border-b border-white/[0.04] ${isSel ? "bg-[var(--status-info)]/15" : "hover:bg-white/[0.04]"}`}
                                            >
                                                <td className="px-3 py-2 t-info">{c.id}</td>
                                                <td className="px-3 py-2">{c.name}</td>
                                                <td className="px-3 py-2">{c.rank}</td>
                                                <td className={`px-3 py-2 ${qual ? "t-nominal" : "t-crit"}`}>{c.qualifications.join(",")}</td>
                                                <td className="px-3 py-2 t-sec">{c.rest_hr_since_duty.toFixed(0)}h</td>
                                                <td className={`px-3 py-2 ${c.fatigue_score > 70 ? "t-crit" : c.fatigue_score > 45 ? "t-warn" : "t-nominal"}`}>
                                                    {c.fatigue_score}
                                                </td>
                                                <td className={`px-3 py-2 ${statusTone}`}>{c.status.toUpperCase()}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Right: assigned + warnings */}
                    <div className="w-1/3 flex flex-col">
                        <div className="px-4 py-2 border-b border-white/10">
                            <div className="label-key">CURRENTLY ASSIGNED ({assignedCrew.length})</div>
                            <div className="uppercase-wide t-muted mt-1">
                                Needed: CP{flight.required_crew.CP} · FO{flight.required_crew.FO} · SC{flight.required_crew.SC} · CC{flight.required_crew.CC}
                            </div>
                        </div>
                        <div className="scroll-area max-h-[180px] border-b border-white/10">
                            {assignedCrew.length === 0 && (
                                <div className="px-4 py-3 t-muted font-mono-jb text-xs">— no crew assigned —</div>
                            )}
                            {assignedCrew.map((c) => (
                                <div key={c.id} className="px-4 py-2 border-b border-white/5 font-mono-jb text-xs flex items-center justify-between">
                                    <div>
                                        <span className="t-info">{c.id}</span> <span className="t-sec">{c.rank}</span> {c.name}
                                    </div>
                                    <button
                                        data-testid={`unassign-${c.id}`}
                                        className="btn btn-danger !py-1 !px-2"
                                        onClick={() => doUnassign(c.id)}
                                    >
                                        REMOVE
                                    </button>
                                </div>
                            ))}
                        </div>

                        <div className="px-4 py-2 border-b border-white/10">
                            <div className="label-key">LEGALITY PRE-CHECK</div>
                        </div>
                        <div className="flex-1 scroll-area p-4">
                            {!selected && <div className="t-muted font-mono-jb text-xs">Select a crew member to run pre-check.</div>}
                            {selected && warnings.length === 0 && (
                                <div className="t-nominal font-mono-jb text-xs" data-testid="legality-clean">
                                    [OK] No legality issues detected. Cleared to roster.
                                </div>
                            )}
                            {warnings.map((w, idx) => (
                                <div
                                    key={idx}
                                    className={`border-l-2 mb-3 pl-3 py-1 ${w.severity === "critical" ? "border-[var(--status-critical)]" : "border-[var(--status-warning)]"}`}
                                    data-testid={`warning-${w.code}`}
                                >
                                    <div className={`font-mono-jb text-xs uppercase tracking-widest ${w.severity === "critical" ? "t-crit" : "t-warn"}`}>
                                        [{w.severity.toUpperCase()}] {w.code}
                                    </div>
                                    <div className="mt-1">{w.message}</div>
                                    <div className="uppercase-wide t-muted mt-1">REF: {w.rule_ref}</div>
                                </div>
                            ))}
                            {error && <div className="t-crit font-mono-jb text-xs mt-2">ERR: {error}</div>}
                        </div>

                        <div className="border-t border-white/10 px-4 py-3 flex items-center gap-2">
                            <button
                                data-testid="assign-confirm-btn"
                                className="btn btn-primary"
                                disabled={!selected || busy || hasCritical}
                                onClick={() => doAssign(false)}
                            >
                                {busy ? "..." : "ASSIGN"}
                            </button>
                            {hasCritical && (
                                <button
                                    data-testid="assign-force-btn"
                                    className="btn btn-danger"
                                    disabled={!selected || busy}
                                    onClick={() => doAssign(true)}
                                >
                                    OVERRIDE
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
