import WarningBlock from "../WarningBlock";
import { delayTone, DELAY_WARN_MIN } from "../../lib/status";
import useModalDialog from "../../lib/useModalDialog";
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
    grounded: "t-crit",
};

/** A rotation's tone comes from how late it actually is. "delayed" spans
 *  everything from 16 minutes to three hours, and colouring all of it amber
 *  disagreed with the timeline and roster board, which both go red at 60. */
function rotationTone(r) {
    if (r.status === "cancelled" || r.status === "grounded") return "t-crit";
    if (r.delay_min > DELAY_WARN_MIN) return delayTone(r.delay_min);
    return STATUS_TONE[r.status] || "t-sec";
}

/**
 * Where a tail will be, and when it is next free, immediately before `beforeIso`.
 *
 * `fleet[].rotations` (with first_dep/last_arr) and `min_turnaround_min` have
 * been in the payload all along and were referenced nowhere — so the reassign
 * decision, which IS "which tail is where and when", was made blind and the
 * position only surfaced afterwards as a critical warning. Classic
 * pick-then-discover.
 */
function tailPosition(ac, beforeIso, hub) {
    const rots = (ac.rotations || [])
        .filter((r) => r.last_arr && r.last_arr <= beforeIso)
        .sort((a, b) => (a.last_arr < b.last_arr ? -1 : 1));
    if (!rots.length) {
        const next = (ac.rotations || []).find((r) => r.first_dep > beforeIso);
        return { at: next ? next.route?.slice(0, 3) || hub : hub, freeFrom: null };
    }
    const last = rots[rots.length - 1];
    const dest = last.route ? last.route.slice(-3) : hub;
    return { at: dest, freeFrom: last.last_arr };
}

function minutesBetween(aIso, bIso) {
    return Math.round((new Date(bIso) - new Date(aIso)) / 60000);
}

export default function AircraftControl({ state, onChanged }) {
    const [view, setView] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState("ALL");
    const [reassign, setReassign] = useState(null); // the rotation being reassigned
    const [rtzMode, setRtzMode] = useState(false);
    const [rtzSelected, setRtzSelected] = useState(() => new Set());
    const [rtzPreview, setRtzPreview] = useState(null);
    const [rtzBusy, setRtzBusy] = useState(false);
    const [rtzError, setRtzError] = useState(null);

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

    function toggleRtzMode() {
        setRtzMode((m) => !m);
        setRtzSelected(new Set());
        setRtzPreview(null);
        setRtzError(null);
    }

    function toggleRtzPairing(pairingId) {
        setRtzSelected((prev) => {
            const next = new Set(prev);
            if (next.has(pairingId)) next.delete(pairingId);
            else next.add(pairingId);
            return next;
        });
    }

    useEffect(() => {
        if (!rtzMode || rtzSelected.size === 0 || !state?.id) {
            setRtzPreview(null);
            return;
        }
        let cancelled = false;
        api.previewResetToZero(state.id, Array.from(rtzSelected))
            .then((p) => {
                if (!cancelled) setRtzPreview(p);
            })
            .catch((e) => {
                if (!cancelled) setRtzError(e?.response?.data?.detail || String(e));
            });
        return () => {
            cancelled = true;
        };
    }, [rtzMode, rtzSelected, state?.id]);

    async function confirmResetToZero() {
        if (rtzSelected.size === 0) return;
        setRtzBusy(true);
        setRtzError(null);
        try {
            const res = await api.resetToZero(state.id, Array.from(rtzSelected));
            if (!res.applied) {
                setRtzError(res.warnings?.map((w) => w.message).join(" ") || "Reset failed.");
                return;
            }
            toggleRtzMode();
            await load();
            if (onChanged) onChanged();
        } catch (e) {
            setRtzError(e?.response?.data?.detail || String(e));
        } finally {
            setRtzBusy(false);
        }
    }

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
                <button
                    data-testid="rtz-toggle"
                    className={`btn ${rtzMode ? "btn-primary" : ""}`}
                    style={!rtzMode ? { borderColor: "var(--status-critical)" } : undefined}
                    onClick={toggleRtzMode}
                    title="Pre-emptively cancel a block of pairings to resync the fleet, trading guaranteed cancellation cost for stopping a worse reactionary-delay cascade."
                >
                    {rtzMode ? "✕ CANCEL RESET" : "⚠ RESET TO ZERO"}
                </button>
            </div>

            {rtzMode && (
                <div className="px-4 py-3 border-b border-white/10 flex items-center gap-4 flex-wrap" data-testid="rtz-bar" style={{ borderTop: "2px solid var(--status-critical)" }}>
                    <div className="uppercase-wide t-crit">RESET TO ZERO — {rtzSelected.size} PAIRING(S) SELECTED</div>
                    {rtzSelected.size === 0 && (
                        <div className="t-muted font-mono-jb text-xs">Check pairings below to build the reset block.</div>
                    )}
                    {rtzPreview && (
                        <div className="font-mono-jb text-xs flex items-center gap-4" data-testid="rtz-preview">
                            <span className="t-warn">COST ${rtzPreview.cost_usd.toLocaleString()}</span>
                            <span className="t-muted">{rtzPreview.cancel_pax} PAX DISRUPTED</span>
                            <span className={rtzPreview.reactionary_avoided_min > 0 ? "t-nominal" : "t-muted"}>
                                −{rtzPreview.reactionary_avoided_min}min NETWORK REACTIONARY DELAY
                            </span>
                        </div>
                    )}
                    {rtzError && <div className="t-crit font-mono-jb text-xs">{rtzError}</div>}
                    <div className="flex-1" />
                    <button
                        data-testid="rtz-confirm"
                        className="btn btn-primary"
                        disabled={rtzSelected.size === 0 || rtzBusy || rtzPreview?.has_critical}
                        onClick={confirmResetToZero}
                    >
                        {rtzBusy ? "…" : "CONFIRM RESET"}
                    </button>
                </div>
            )}

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
                                {ac.grounded ? "⛔ GROUNDED" : ac.spare ? "◆ SPARE" : ac.status}
                            </div>
                            {!ac.spare && (
                                <div className="uppercase-wide t-muted mt-0.5">
                                    {ac.rotation_count} ROT · {ac.block_hours}H
                                </div>
                            )}
                            {ac.mel_items && ac.mel_items.length > 0 && (
                                <div
                                    className={`uppercase-wide mt-0.5 ${ac.grounded ? "t-crit" : "t-warn"}`}
                                    data-testid={`mel-badge-${ac.reg}`}
                                    title={ac.mel_items.map((m) => `Cat ${m.category}: ${m.note}`).join(" · ")}
                                >
                                    MEL ×{ac.mel_items.length} (
                                    {ac.mel_items.map((m) => `${m.expired ? "EXPIRED" : `${m.days_remaining}d`}`).join(", ")}
                                    )
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
                            {rtzMode && <th className="text-left px-3 py-2 border-b border-white/10">RTZ</th>}
                            <th className="text-left px-3 py-2 border-b border-white/10">ROTATION</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">ROUTE</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">A/C</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STD → STA</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">BLK</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">PAX</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">TAIL</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STATUS</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">REACT.</th>
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
                                {rtzMode && (
                                    <td className="px-3 py-2">
                                        <input
                                            type="checkbox"
                                            data-testid={`rtz-check-${r.pairing_id}`}
                                            disabled={!r.resettable}
                                            checked={rtzSelected.has(r.pairing_id)}
                                            onChange={() => toggleRtzPairing(r.pairing_id)}
                                            title={r.resettable ? "Include in reset block" : "Nothing left to cancel"}
                                        />
                                    </td>
                                )}
                                <td className="px-3 py-2 t-info">{r.callsigns.join(" / ")}</td>
                                <td className="px-3 py-2">{r.route}</td>
                                <td className="px-3 py-2 t-sec">{r.aircraft_type}</td>
                                <td className="px-3 py-2 t-sec">
                                    {fmtClock(r.std)} → {fmtClock(r.sta)}
                                </td>
                                <td className="px-3 py-2 t-sec">{hhmm(r.block_min)}</td>
                                <td className="px-3 py-2 t-sec">{r.pax}</td>
                                <td className="px-3 py-2 t-info">{r.aircraft_reg}</td>
                                <td className={`px-3 py-2 ${rotationTone(r)}`}>
                                    {r.status.toUpperCase()}
                                </td>
                                <td className={`px-3 py-2 ${r.reactionary_min > 0 ? "t-warn" : "t-muted"}`}>
                                    {r.reactionary_min > 0 ? `+${r.reactionary_min}m` : "—"}
                                </td>
                                <td className="px-3 py-2 text-right">
                                    <button
                                        data-testid={`reassign-${r.pairing_id}`}
                                        className="btn btn-primary"
                                        disabled={!r.reassignable || rtzMode}
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
                    minTurn={view.min_turnaround_min}
                    hub={view.hub || "LHR"}
                    onClose={() => setReassign(null)}
                    onAssigned={onReassigned}
                />
            )}
        </div>
    );
}

const VERDICT_TONE = { OPTIMAL: "t-nominal", GOOD: "t-info", SUBOPTIMAL: "t-warn" };

function ReassignModal({ state, rotation, fleet, minTurn = 45, hub = "LHR", onClose, onAssigned }) {
    const [selected, setSelected] = useState(null);
    const [warnings, setWarnings] = useState([]);
    const [ferryWarnings, setFerryWarnings] = useState(null); // null = not checked yet
    const [ferryPreview, setFerryPreview] = useState(null); // route + price of the positioning flight
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [grade, setGrade] = useState(null);
    // Off-type tails, priced. The fleet grid above this modal already SHOWS
    // idle widebody spares, so a player could see two aircraft they were not
    // allowed to touch and no hint that anything else existed.
    const [subOptions, setSubOptions] = useState({});
    const [showSubFleet, setShowSubFleet] = useState(false);
    const dialogRef = useModalDialog(onClose);

    // Off-type tails that could cover this rotation at a price. Upgauge only —
    // a smaller aircraft cannot absorb a bigger one's passengers.
    const subFleet = useMemo(
        () =>
            fleet.filter(
                (ac) => ac.type !== rotation.aircraft_type && ac.reg !== rotation.aircraft_reg
            ),
        [fleet, rotation]
    );

    // Same-type tails other than the current one, spares first, then by load.
    const candidates = useMemo(() => {
        const rank = (ac) => {
            if (ac.grounded) return 2;
            return tailPosition(ac, rotation.std, hub).at === rotation.origin ? 0 : 1;
        };
        return fleet
            .filter((ac) => ac.type === rotation.aircraft_type && ac.reg !== rotation.aircraft_reg)
            .sort(
                (a, b) =>
                    rank(a) - rank(b) ||
                    (b.spare ? 1 : 0) - (a.spare ? 1 : 0) ||
                    a.block_min - b.block_min
            );
    }, [fleet, rotation, hub]);

    useEffect(() => {
        if (!selected) {
            setWarnings([]);
            setFerryWarnings(null);
            setFerryPreview(null);
            return;
        }
        let cancelled = false;
        api.checkAircraft(state.id, rotation.pairing_id, selected)
            .then((d) => {
                if (!cancelled) setWarnings(d.warnings || []);
            })
            .catch(() => {});
        // Always preview the ferry option too — if it's crewable and
        // curfew-clear, it can rescue a plain reassignment even before the
        // player finds out the plain path is blocked.
        api.checkFerry(state.id, rotation.pairing_id, selected)
            .then((d) => {
                if (cancelled) return;
                setFerryWarnings(d.warnings || []);
                setFerryPreview(d);
            })
            .catch(() => {
                if (!cancelled) {
                    setFerryWarnings(null);
                    setFerryPreview(null);
                }
            });
        return () => {
            cancelled = true;
        };
    }, [selected, state.id, rotation.pairing_id]);

    // Priced lazily: this is several round-trips and most reassignments never
    // need it.
    useEffect(() => {
        if (!showSubFleet) return undefined;
        let cancelled = false;
        Promise.all(
            subFleet.map((ac) =>
                api
                    .checkSubstitution(state.id, rotation.pairing_id, ac.reg)
                    .then((d) => [ac.reg, d])
                    .catch(() => [ac.reg, null])
            )
        ).then((pairs) => {
            if (!cancelled) setSubOptions(Object.fromEntries(pairs));
        });
        return () => {
            cancelled = true;
        };
    }, [showSubFleet, subFleet, state.id, rotation.pairing_id]);

    async function doSubstitute(reg) {
        setBusy(true);
        setError(null);
        try {
            const res = await api.substituteAircraft(state.id, rotation.pairing_id, reg);
            if (!res.applied) {
                setError(
                    (res.warnings || []).find((w) => w.severity === "critical")?.message ||
                        "Substitution refused."
                );
                return;
            }
            if (res.decision_grade) {
                setGrade({ ...res.decision_grade, substitution: res });
            } else {
                onAssigned();
            }
        } catch (e) {
            setError(String(e));
        } finally {
            setBusy(false);
        }
    }

    const hasCritical = warnings.some((w) => w.severity === "critical");
    const ferryHasCritical = (ferryWarnings || []).some((w) => w.severity === "critical");
    // A ferry only makes sense to offer once the plain reassign is blocked
    // AND the ferry itself is actually viable — crewed (1 Captain + 1 FO,
    // legal under FTL rest/duty rules) and not stuck behind the LHR curfew.
    const canFerry =
        selected && ferryWarnings !== null && !ferryHasCritical && !!ferryPreview?.needs_ferry;
    // Kept for the copy that explains why a blocked reassign still has a way out.
    const canFerryInstead = canFerry && hasCritical;

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
            if (res.decision_grade) {
                // This reassignment resolved a grounded-aircraft incident — show
                // how it graded against the best alternative before closing,
                // rather than silently vanishing the decision's feedback.
                setGrade(res.decision_grade);
                return;
            }
            onAssigned();
        } catch (e) {
            setError(e?.response?.data?.detail || String(e));
        } finally {
            setBusy(false);
        }
    }

    async function doFerry() {
        if (!selected) return;
        setBusy(true);
        setError(null);
        try {
            const res = await api.ferryAircraft(state.id, rotation.pairing_id, selected);
            if (!res.applied) {
                setWarnings(res.warnings || []);
                return;
            }
            if (res.decision_grade) {
                setGrade({ ...res.decision_grade, ferry: res.ferry_flight, ferryCost: res.cost_usd });
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
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="reassign-modal-title"
                tabIndex={-1}
                className="panel w-[820px] max-w-[96vw] max-h-[85vh] flex flex-col"
                style={{ borderTop: "2px solid var(--status-info)" }}
            >
                <div className="px-5 py-3 border-b border-white/10 flex items-center gap-4">
                    <div>
                        <div className="label-key" id="reassign-modal-title">REASSIGN AIRCRAFT</div>
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
                    {grade && (
                        <div data-testid="reassign-decision-grade">
                            <div className="label-key mb-2">DECISION GRADE</div>
                            <div className={`font-azeret text-lg ${VERDICT_TONE[grade.verdict] || "t-sec"}`}>
                                {grade.verdict}
                            </div>
                            {grade.ferry && (
                                <div className="font-mono-jb text-xs mt-2 t-info" data-testid="ferry-summary">
                                    ✈ POSITIONING FLIGHT {grade.ferry.callsign}: {grade.ferry.origin} → {grade.ferry.destination}
                                    ({grade.ferry.block_min}min, empty) — the open leg waits for it to land.
                                    {typeof grade.ferryCost === "number" && ` Cost: $${grade.ferryCost.toLocaleString()}.`}
                                </div>
                            )}
                            <div className="font-mono-jb text-xs mt-2 t-sec">
                                YOU CHOSE {grade.player_choice} — total impact $
                                {grade.player_impact_usd?.toLocaleString()}
                            </div>
                            <div className="font-mono-jb text-xs mt-1 t-muted">
                                BEST AVAILABLE WAS {grade.best_choice === "cancel" ? "CANCEL" : grade.best_choice} — $
                                {grade.best_impact_usd?.toLocaleString()}
                                {grade.delta_usd > 0 &&
                                    ` (this choice cost $${grade.delta_usd.toLocaleString()} more than optimal)`}
                                {grade.delta_usd <= 0 && " — you found it."}
                            </div>
                        </div>
                    )}
                    {!grade && (
                    <>
                    <div className="label-key mb-2">
                        AVAILABLE {rotation.aircraft_type} TAILS ({candidates.length})
                    </div>
                    {candidates.length === 0 && (
                        <div className="t-muted font-mono-jb text-xs">
                            No other {rotation.aircraft_type} in the fleet.
                        </div>
                    )}
                    {subFleet.length > 0 && (
                        <div className="mt-4" data-testid="sub-fleet-section">
                            <button
                                className="label-key flex items-baseline gap-1.5"
                                onClick={() => setShowSubFleet((v) => !v)}
                                aria-expanded={showSubFleet}
                                data-testid="sub-fleet-toggle"
                            >
                                <span aria-hidden="true">{showSubFleet ? "▾" : "▸"}</span>
                                SUB-FLEET OPTIONS ({subFleet.length})
                            </button>
                            {showSubFleet && (
                                <div className="mt-2 flex flex-col gap-2">
                                    {subFleet.map((ac) => {
                                        const pv = subOptions[ac.reg];
                                        const blocked = pv?.warnings?.find(
                                            (w) => w.severity === "critical"
                                        );
                                        const ci = pv?.crew_impact;
                                        return (
                                            <div
                                                key={ac.reg}
                                                className="border border-white/15 px-3 py-2 font-mono-jb text-xs"
                                                data-testid={`sub-cand-${ac.reg}`}
                                            >
                                                <div className="flex items-center gap-3 flex-wrap">
                                                    <span className="t-info">{ac.reg}</span>
                                                    <span className="t-muted">{ac.type}</span>
                                                    {pv && !blocked && (
                                                        <>
                                                            <span className="t-warn">
                                                                ${pv.cost_usd.toLocaleString()}
                                                            </span>
                                                            <span className="t-muted">
                                                                {pv.seats_from}→{pv.seats_to} seats ·
                                                                upgauge
                                                            </span>
                                                            <button
                                                                className="btn btn-primary ml-auto"
                                                                disabled={busy || !ci?.crewable}
                                                                onClick={() => doSubstitute(ac.reg)}
                                                                data-testid={`substitute-${ac.reg}`}
                                                            >
                                                                {busy ? "…" : "SUBSTITUTE"}
                                                            </button>
                                                        </>
                                                    )}
                                                    {!pv && (
                                                        <span className="t-muted">pricing…</span>
                                                    )}
                                                </div>
                                                {blocked && (
                                                    <div className="mt-1 t-crit">
                                                        [{blocked.code}] {blocked.message}
                                                    </div>
                                                )}
                                                {pv && !blocked && ci && (
                                                    <div
                                                        className={`mt-1 ${
                                                            ci.crewable ? "t-muted" : "t-crit"
                                                        }`}
                                                    >
                                                        {ci.crewable
                                                            ? `Crewable: needs CP${ci.open_ranks.CP}/FO${ci.open_ranks.FO}/SC${ci.open_ranks.SC}/CC${ci.open_ranks.CC}, ${ci.stood_down.length} rostered crew stand down as not type-rated.`
                                                            : `NOT CREWABLE: needs CP${ci.open_ranks.CP}/FO${ci.open_ranks.FO}/SC${ci.open_ranks.SC}/CC${ci.open_ranks.CC}, only CP${ci.rated_available.CP}/FO${ci.rated_available.FO}/SC${ci.rated_available.SC}/CC${ci.rated_available.CC} rated and free.`}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    )}
                    <div className="flex flex-col gap-2">
                        {candidates.map((ac) => {
                            const isSel = selected === ac.reg;
                            const pos = tailPosition(ac, rotation.std, hub);
                            const turn = pos.freeFrom
                                ? minutesBetween(pos.freeFrom, rotation.std)
                                : null;
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
                                        {ac.grounded && (
                                            <span className="uppercase-wide t-crit">⛔ MEL GROUNDED</span>
                                        )}
                                    </div>
                                    <div
                                        className="mt-1 flex items-center gap-3 text-[10px]"
                                        data-testid={`reassign-cand-position-${ac.reg}`}
                                    >
                                        <span className={pos.at === rotation.origin ? "t-nominal" : "t-warn"}>
                                            AT {pos.at}
                                            {pos.at !== rotation.origin ? " · NEEDS FERRY" : ""}
                                        </span>
                                        <span className="t-muted">
                                            {pos.freeFrom
                                                ? `FREE FROM ${pos.freeFrom.slice(11, 16)}Z`
                                                : "FREE ALL DAY"}
                                        </span>
                                        {turn !== null && (
                                            <span className={turn < minTurn ? "t-warn" : "t-muted"}>
                                                TURN {turn}M{turn < minTurn ? ` < MIN ${minTurn}M` : ""}
                                            </span>
                                        )}
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
                                    <WarningBlock key={idx} warning={w} testIdPrefix="reassign-warning" />
                                ))
                            )}
                            {error && <div className="t-crit font-mono-jb text-xs mt-2">ERR: {error}</div>}
                        </div>
                    )}

                    {selected && ferryWarnings !== null && (
                        <div className="mt-4" data-testid="ferry-option-check">
                            <div className="label-key mb-2">FERRY OPTION</div>
                            {ferryPreview?.needs_ferry && (
                                <div
                                    className="font-mono-jb text-xs mb-2 flex items-center gap-3"
                                    data-testid="ferry-cost"
                                >
                                    <span className="t-warn">
                                        COST ${ferryPreview.cost_usd.toLocaleString()}
                                    </span>
                                    <span className="t-muted">
                                        {ferryPreview.ferry_flight.origin}→
                                        {ferryPreview.ferry_flight.destination} empty,{" "}
                                        {ferryPreview.ferry_flight.block_min}min block — dispatch fee
                                        plus fuel/crew for a zero-revenue sector.
                                    </span>
                                </div>
                            )}
                            {ferryPreview?.crew?.captain && (
                                <div
                                    className="font-mono-jb text-[10px] mb-2 flex flex-wrap items-center gap-x-3"
                                    data-testid="ferry-crew-cost"
                                >
                                    <span className="t-sec">
                                        BURNS {ferryPreview.crew.captain} + {ferryPreview.crew.first_officer}
                                    </span>
                                    <span className="t-muted">
                                        +{ferryPreview.crew.fdp_consumed_min}min FDP each
                                    </span>
                                    <span
                                        className={
                                            ferryPreview.crew.standby_remaining?.CP <= 1
                                                ? "t-crit"
                                                : "t-muted"
                                        }
                                    >
                                        {ferryPreview.crew.standby_remaining?.CP} CP /{" "}
                                        {ferryPreview.crew.standby_remaining?.FO} FO LEFT ON STANDBY
                                    </span>
                                </div>
                            )}
                            {ferryWarnings.length === 0 ? (
                                <div className="t-nominal font-mono-jb text-xs" data-testid="ferry-clean">
                                    [OK] {selected} can be positioned empty — 1 Captain + 1 FO available and
                                    legal (EASA FTL rest/duty), no curfew block. Cleared to ferry.
                                </div>
                            ) : (
                                ferryWarnings.map((w, idx) => (
                                    <WarningBlock key={idx} warning={w} testIdPrefix="ferry-warning" />
                                ))
                            )}
                        </div>
                    )}
                    </>
                    )}
                </div>

                <div className="border-t border-white/10 px-4 py-3 flex items-center gap-2">
                    {grade ? (
                        <button data-testid="reassign-grade-done-btn" className="btn btn-primary" onClick={onAssigned}>
                            DONE
                        </button>
                    ) : (
                        <>
                            <button
                                data-testid="reassign-confirm-btn"
                                className="btn btn-primary"
                                disabled={!selected || busy || hasCritical}
                                onClick={doAssign}
                            >
                                {busy ? "…" : "ASSIGN TAIL"}
                            </button>
                            {canFerry && (
                                <button
                                    data-testid="reassign-ferry-btn"
                                    className="btn btn-primary"
                                    disabled={busy}
                                    onClick={doFerry}
                                    title="Dispatch this tail EMPTY to reposition it, then hand it the open leg once it lands"
                                >
                                    {busy
                                        ? "…"
                                        : ferryPreview?.needs_ferry
                                          ? `✈ FERRY & CONTINUE — $${ferryPreview.cost_usd.toLocaleString()}`
                                          : "✈ FERRY & CONTINUE"}
                                </button>
                            )}
                            {hasCritical && !canFerry && (
                                <span className="uppercase-wide t-crit">
                                    Aircraft constraints are hard — no override.
                                </span>
                            )}
                            {canFerryInstead && (
                                <span className="uppercase-wide t-warn">
                                    Reassign is blocked — but the tail is crewable and curfew-clear, so it can
                                    be positioned instead.
                                </span>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
