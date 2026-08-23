import React, { useCallback, useEffect, useState } from "react";
import { api } from "../../api";

const WHY_LABEL = {
    unreachable_duty: "CANNOT REACH NEXT DUTY",
    no_way_back: "AWAY FROM BASE, NOTHING ROSTERED",
};

/**
 * The crew disposition desk.
 *
 * The engine has always known crew have a physical position, but the only
 * thing it did with that was raise a warning ending "position them or replace
 * them" — neither of which the player could actually do. This is where those
 * crew get dealt with.
 *
 * Deliberately NOT a list of everyone away from base: a crew night-stopping at
 * HKG with the HKG-LHR return already rostered is ordinary long-haul, not a
 * problem, and forty-nine of them would bury the handful that need a call.
 */
export default function CrewDisposition({ state, onChanged }) {
    const [rows, setRows] = useState([]);
    const [handled, setHandled] = useState(0);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState(null);
    const [note, setNote] = useState(null);

    const load = useCallback(() => {
        return api
            .crewDisposition(state.id)
            .then((d) => {
                setRows(d.disposition || []);
                setHandled(d.handled_today || 0);
                setLoading(false);
            })
            .catch((e) => {
                setError(String(e));
                setLoading(false);
            });
    }, [state.id]);

    useEffect(() => {
        load();
    }, [load, state.clock, state.phase]);

    async function dispose(crewId, action) {
        setBusy(`${crewId}:${action}`);
        setError(null);
        try {
            const res = await api.disposeCrew(state.id, crewId, action);
            if (!res.applied) {
                setError(res.reason || "Not available.");
            } else {
                setNote(res.note);
                await load();
                onChanged?.();
            }
        } catch (e) {
            setError(String(e));
        } finally {
            setBusy(null);
        }
    }

    return (
        <div className="h-full flex flex-col" data-testid="crew-disposition">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">CREW DISPOSITION</div>
                    <div className="font-azeret text-lg">OUT OF POSITION</div>
                </div>
                <div className="flex-1" />
                <span className="font-mono-jb text-xs t-muted">
                    {rows.length} REQUIRING A DECISION
                    {handled > 0 && ` · ${handled} HANDLED TODAY`}
                </span>
            </div>

            {note && (
                <div className="px-4 py-2 border-b border-white/10 font-mono-jb text-xs t-nominal">
                    [OK] {note}
                </div>
            )}
            {error && (
                <div className="px-4 py-2 border-b border-[var(--status-critical)] font-mono-jb text-xs t-crit">
                    ERR: {error}
                </div>
            )}

            <div className="flex-1 scroll-area">
                {loading && (
                    <div className="p-6 t-muted font-mono-jb text-xs">[SYS] Reading crew positions…</div>
                )}
                {!loading && rows.length === 0 && (
                    <div className="p-6 t-nominal font-mono-jb text-xs" data-testid="disposition-clear">
                        [OK] Every crew is either at base or has a duty out of the station they are
                        standing in. Nothing to decide.
                    </div>
                )}

                {rows.map((r) => (
                    <div
                        key={r.crew_id}
                        className={`border-b border-white/[0.06] border-l-4 px-4 py-3 ${
                            r.why === "unreachable_duty"
                                ? "border-l-[var(--status-critical)]"
                                : "border-l-[var(--status-warning)]"
                        }`}
                        data-testid={`disposition-${r.crew_id}`}
                    >
                        <div className="flex items-center gap-3 flex-wrap">
                            <span className="badge t-info">{r.crew_id}</span>
                            <span className="font-azeret">{r.name}</span>
                            <span className="badge t-sec">{r.rank}</span>
                            <span className="uppercase-wide t-warn">AT {r.at}</span>
                            <span className="uppercase-wide t-muted">BASE {r.base}</span>
                            <span
                                className={`uppercase-wide ml-auto ${
                                    r.why === "unreachable_duty" ? "t-crit" : "t-warn"
                                }`}
                            >
                                {WHY_LABEL[r.why] || r.why}
                            </span>
                        </div>

                        <div className="mt-1 font-mono-jb text-xs t-sec">
                            {r.next_duty ? (
                                <>
                                    NEXT DUTY {r.next_duty.callsign} {r.next_duty.origin}→
                                    {r.next_duty.destination} {r.next_duty.std.slice(11, 16)}Z
                                    {!r.next_duty.reachable && (
                                        <span className="t-crit"> — departs {r.next_duty.origin}, they are at {r.at}</span>
                                    )}
                                </>
                            ) : (
                                <span className="t-muted">No duty rostered out of {r.at}.</span>
                            )}
                            {r.slack_min !== null && r.slack_min !== undefined && (
                                <span className={r.slack_min < 60 ? "t-crit" : "t-muted"}>
                                    {"  ·  "}
                                    {r.slack_min}m FDP SLACK
                                </span>
                            )}
                        </div>

                        <div className="mt-2 flex flex-col gap-1">
                            {r.options.map((o) => (
                                <div key={o.action} className="flex items-baseline gap-3 font-mono-jb text-xs">
                                    <button
                                        className={`btn ${o.feasible ? "btn-primary" : ""}`}
                                        disabled={!o.feasible || busy !== null}
                                        onClick={() => dispose(r.crew_id, o.action)}
                                        data-testid={`dispose-${r.crew_id}-${o.action}`}
                                    >
                                        {busy === `${r.crew_id}:${o.action}` ? "…" : o.label}
                                    </button>
                                    {o.cost_usd > 0 && (
                                        <span className="t-warn">${o.cost_usd.toLocaleString()}</span>
                                    )}
                                    <span className={o.feasible ? "t-muted" : "t-crit"}>
                                        {o.detail || o.reason}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
