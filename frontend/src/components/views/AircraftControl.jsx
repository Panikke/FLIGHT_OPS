import React, { useEffect, useState, useCallback, useMemo } from "react";
import { api } from "../../api";

function fmtClock(iso) {
    if (!iso) return "--:--";
    return iso.slice(11, 16);
}

function hhmm(mins) {
    return `${Math.floor(mins / 60)}h${(mins % 60).toString().padStart(2, "0")}`;
}

const STATUS_TONE = {
    spare: "t-stby",
    "in service": "t-nominal",
    delayed: "t-warn",
    airborne: "t-info",
    "day done": "t-muted",
    landed: "t-muted",
    idle: "t-muted",
    scheduled: "t-nominal",
    boarding: "t-info",
    cancelled: "t-crit",
};

export default function AircraftControl({ state, onChanged }) {
    const [view, setView] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState("ALL");
    const [reassign, setReassign] = useState(null); // the rotation being reassigned

    const load = useCallback(async () => {
        if (!state?.id) return;
        try {
            const v = await api.aircraftControl(state.id);
            setView(v);
            setError(null);
        } catch (e) {
            setError(e?.message || "failed to load fleet");
        } finally {
            setLoading(false);
        }
    }, [state?.id]);

    useEffect(() => {
        load();
    }, [load, state?.day_number, state?.phase, state?.clock]);

    const onReassigned = useCallback(async () => {
        setReassign(null);
        await load();
        if (onChanged) onChanged();
    }, [load, onChanged]);

    const rotations = useMemo(() => {
        if (!view) return [];
        let list = view.rotations;
        if (filter !== "ALL") list = list.filter((r) => r.aircraft_type === filter);
        return list;
    }, [view, filter]);

    if (loading) {
        return <div className="p-6 t-muted font-mono-jb text-xs">[SYS] Loading fleet…</div>;
    }
    if (error) {
        return <div className="p-6 t-crit font-mono-jb text-xs">ERR: {error}</div>;
    }

    return (
        <div className="h-full flex flex-col" data-testid="aircraft-control">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3 flex-wrap">
                <div>
                    <div className="label-key">AIRCRAFT CONTROL</div>
                    <div className="font-azeret text-lg">FLEET &amp; TAIL ASSIGNMENT</div>
                </div>
                <div className="flex-1" />
                <div className="uppercase-wide t-sec">FILTER</div>
                {["ALL", "A320", "A350", "B777"].map((t) => (
                    <button
                        key={t}
                        data-testid={`ac-filter-${t}`}
                        className={`btn ${filter === t ? "btn-primary" : ""}`}
                        onClick={() => setFilter(t)}
                    >
                        {t}
                    </button>
                ))}
            </div>

            {/* Fleet summary strip */}
            <div className="px-4 py-3 border-b border-white/10 flex gap-3 flex-wrap" data-testid="fleet-strip">
                {view.fleet
                    .filter((ac) => filter === "ALL" || ac.type === filter)
                    .map((ac) => (
                        <div
                            key={ac.reg}
                            data-testid={`tail-${ac.reg}`}
                            className={`border px-3 py-2 font-mono-jb text-xs ${
                                ac.spare ? "border-[var(--status-standby)]/50" : "border-white/15"
                            }`}
                            title={`${ac.rotation_count} rotation(s), ${ac.block_hours}h block`}
                        >
                            <div className="flex items-center gap-2">
                                <span className="t-info">{ac.reg}</span>
                                <span className="t-muted">{ac.type}</span>
                            </div>
                            <div className={`uppercase-wide mt-0.5 ${STATUS_TONE[ac.status] || "t-sec"}`}>
                                {ac.spare ? "◆ SPARE" : ac.status}
                            </div>
                            {!ac.spare && (
                                <div className="uppercase-wide t-muted mt-0.5">
                                    {ac.rotation_count} ROT · {ac.block_hours}H
                                </div>
                            )}
                        </div>
                    ))}
            </div>

            {/* Rotations table */}
            <div className="flex-1 scroll-area">
                <table className="w-full text-xs" data-testid="rotations-table">
                    <thead className="sticky top-0 bg-[#050505] z-10">
                        <tr className="uppercase-wide t-muted">
                            <th className="text-left px-3 py-2 border-b border-white/10">ROTATION</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">ROUTE</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">A/C</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STD → STA</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">BLK</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">PAX</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">TAIL</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STATUS</th>
                            <th className="text-right px-3 py-2 border-b border-white/10">ACT</th>
                        </tr>
                    </thead>
                    <tbody className="zebra font-mono-jb">
                        {rotations.map((r) => (
                            <tr
                                key={r.pairing_id}
                                className="border-b border-white/[0.04] hover:bg-white/[0.03]"
                                data-testid={`rotation-${r.pairing_id}`}
                            >
                                <td className="px-3 py-2 t-info">{r.callsigns.join(" / ")}</td>
                                <td className="px-3 py-2">{r.route}</td>
                                <td className="px-3 py-2 t-sec">{r.aircraft_type}</td>
                                <td className="px-3 py-2 t-sec">
                                    {fmtClock(r.std)} → {fmtClock(r.sta)}
                                </td>
                                <td className="px-3 py-2 t-sec">{hhmm(r.block_min)}</td>
                                <td className="px-3 py-2 t-sec">{r.pax}</td>
                                <td className="px-3 py-2 t-info">{r.aircraft_reg}</td>
                                <td className={`px-3 py-2 ${STATUS_TONE[r.status] || "t-sec"}`}>
                                    {r.status.toUpperCase()}
                                </td>
                                <td className="px-3 py-2 text-right">
                                    <button
                                        data-testid={`reassign-${r.pairing_id}`}
                                        className="btn btn-primary"
                                        disabled={!r.reassignable}
                                        title={r.reassignable ? "Assign a different tail" : "Rotation is underway — cannot reassign"}
                                        onClick={() => setReassign(r)}
                                    >
                                        REASSIGN
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {reassign && (
                <ReassignModal
                    state={state}
                    rotation={reassign}
                    fleet={view.fleet}
                    onClose={() => setReassign(null)}
                    onAssigned={onReassigned}
                />
            )}
        </div>
    );
}

function ReassignModal({ state, rotation, fleet, onClose, onAssigned }) {
    const [selected, setSelected] = useState(null);
    const [warnings, setWarnings] = useState([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    // Same-type tails other than the current one, spares first, then by load.
    const candidates = useMemo(() => {
        return fleet
            .filter((ac) => ac.type === rotation.aircraft_type && ac.reg !== rotation.aircraft_reg)
            .sort((a, b) => (b.spare ? 1 : 0) - (a.spare ? 1 : 0) || a.block_min - b.block_min);
    }, [fleet, rotation]);

    useEffect(() => {
        if (!selected) {
            setWarnings([]);
            return;
        }
        let cancelled = false;
        api.checkAircraft(state.id, rotation.pairing_id, selected)
            .then((d) => {
                if (!cancelled) setWarnings(d.warnings || []);
            })
            .catch(() => {});
        return () => {
            cancelled = true;
        };
    }, [selected, state.id, rotation.pairing_id]);

    const hasCritical = warnings.some((w) => w.severity === "critical");

    async function doAssign() {
        if (!selected) return;
        setBusy(true);
        setError(null);
        try {
            const res = await api.assignAircraft(state.id, rotation.pairing_id, selected);
            if (!res.applied) {
                setWarnings(res.warnings || []);
                return;
            }
            onAssigned();
        } catch (e) {
            setError(e?.response?.data?.detail || String(e));
        } finally {
            setBusy(false);
        }
    }

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-md bg-black/80"
            data-testid="reassign-modal"
        >
            <div className="panel w-[820px] max-w-[96vw] max-h-[85vh] flex flex-col" style={{ borderTop: "2px solid var(--status-info)" }}>
                <div className="px-5 py-3 border-b border-white/10 flex items-center gap-4">
                    <div>
                        <div className="label-key">REASSIGN AIRCRAFT</div>
                        <div className="font-azeret text-lg">
                            {rotation.callsigns.join(" / ")} · {rotation.route} · {rotation.aircraft_type}
                        </div>
                        <div className="uppercase-wide t-muted mt-1">
                            {fmtClock(rotation.std)} → {fmtClock(rotation.sta)}Z · currently{" "}
                            <span className="t-info">{rotation.aircraft_reg}</span>
                        </div>
                    </div>
                    <div className="flex-1" />
                    <button data-testid="close-reassign-modal" className="btn" onClick={onClose}>
                        CLOSE
                    </button>
                </div>

                <div className="flex-1 scroll-area p-4">
                    <div className="label-key mb-2">
                        AVAILABLE {rotation.aircraft_type} TAILS ({candidates.length})
                    </div>
                    {candidates.length === 0 && (
                        <div className="t-muted font-mono-jb text-xs">
                            No other {rotation.aircraft_type} in the fleet.
                        </div>
                    )}
                    <div className="flex flex-col gap-2">
                        {candidates.map((ac) => {
                            const isSel = selected === ac.reg;
                            return (
                                <button
                                    key={ac.reg}
                                    data-testid={`reassign-cand-${ac.reg}`}
                                    onClick={() => setSelected(ac.reg)}
                                    className={`text-left border px-3 py-2 font-mono-jb text-xs cursor-pointer ${
                                        isSel
                                            ? "border-[var(--status-info)] bg-[var(--status-info)]/10"
                                            : "border-white/15 hover:bg-white/[0.04]"
                                    }`}
                                >
                                    <div className="flex items-center gap-3">
                                        <span className="t-info">{ac.reg}</span>
                                        <span className="t-muted">{ac.type}</span>
                                        <span className={`uppercase-wide ${ac.spare ? "t-stby" : STATUS_TONE[ac.status] || "t-sec"}`}>
                                            {ac.spare ? "◆ SPARE (on stand)" : `${ac.rotation_count} rotation(s) · ${ac.block_hours}h`}
                                        </span>
                                    </div>
                                </button>
                            );
                        })}
                    </div>

                    {selected && (
                        <div className="mt-4">
                            <div className="label-key mb-2">COMPATIBILITY CHECK</div>
                            {warnings.length === 0 ? (
                                <div className="t-nominal font-mono-jb text-xs" data-testid="reassign-clean">
                                    [OK] {selected} is free and type-compatible. Cleared to assign.
                                </div>
                            ) : (
                                warnings.map((w, idx) => (
                                    <div
                                        key={idx}
                                        className="border-l-2 mb-3 pl-3 py-1 border-[var(--status-critical)]"
                                        data-testid={`reassign-warning-${w.code}`}
                                    >
                                        <div className="font-mono-jb text-xs uppercase tracking-widest t-crit">
                                            [{w.severity.toUpperCase()}] {w.code}
                                        </div>
                                        <div className="mt-1">{w.message}</div>
                                        <div className="uppercase-wide t-muted mt-1">REF: {w.rule_ref}</div>
                                    </div>
                                ))
                            )}
                            {error && <div className="t-crit font-mono-jb text-xs mt-2">ERR: {error}</div>}
                        </div>
                    )}
                </div>

                <div className="border-t border-white/10 px-4 py-3 flex items-center gap-2">
                    <button
                        data-testid="reassign-confirm-btn"
                        className="btn btn-primary"
                        disabled={!selected || busy || hasCritical}
                        onClick={doAssign}
                    >
                        {busy ? "…" : "ASSIGN TAIL"}
                    </button>
                    {hasCritical && (
                        <span className="uppercase-wide t-crit">
                            Aircraft constraints are hard — no override.
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
