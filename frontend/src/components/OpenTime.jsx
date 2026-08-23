import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { severityTone } from "../lib/status";

/**
 * OPEN TIME — flying with nobody on it.
 *
 * `roster_completeness` has computed this since the roster board was written,
 * and it was consumed only as an OPEN_SECTOR warning string. Real rostering
 * systems make it the first thing on the screen and the thing you assign FROM,
 * which is what the term means in the trade.
 */
export default function OpenTime({ state, onChanged }) {
    const [rows, setRows] = useState([]);
    const [busy, setBusy] = useState(null);
    const [error, setError] = useState(null);
    const [open, setOpen] = useState(null);

    const load = useCallback(
        () =>
            api
                .openTime(state.id)
                .then((d) => setRows(d.open_time || []))
                .catch((e) => setError(String(e))),
        [state.id]
    );

    useEffect(() => {
        load();
        // Keyed on the state object: assigning a crew changes neither the
        // clock nor any count this component could otherwise watch.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [state]);

    async function assign(flightId, crewId) {
        setBusy(`${flightId}:${crewId}`);
        setError(null);
        try {
            const res = await api.assign(state.id, flightId, crewId);
            if (!res.applied) {
                setError(
                    (res.warnings || []).find((w) => w.severity === "critical")?.message ||
                        "Assignment refused."
                );
            } else {
                await load();
                onChanged?.();
            }
        } catch (e) {
            setError(String(e));
        } finally {
            setBusy(null);
        }
    }

    const positions = rows.reduce((n, r) => n + r.short_by, 0);

    return (
        <div className="w-[340px] flex-shrink-0 border-l border-white/10 flex flex-col" data-testid="open-time">
            <div className="px-3 py-3 border-b border-white/10">
                <div className="label-key">OPEN TIME</div>
                <div className="font-mono-jb text-xs t-muted mt-0.5">
                    {rows.length} SECTORS · {positions} POSITIONS UNCOVERED
                </div>
            </div>

            {error && (
                <div className="px-3 py-2 border-b border-[var(--status-critical)] font-mono-jb text-[10px] t-crit">
                    {error}
                </div>
            )}

            <div className="flex-1 scroll-area">
                {rows.length === 0 && (
                    <div className="p-4 font-mono-jb text-xs t-nominal" data-testid="open-time-clear">
                        [OK] Every sector is fully crewed.
                    </div>
                )}
                {rows.map((r) => {
                    const isOpen = open === r.flight_id;
                    return (
                        <div
                            key={r.flight_id}
                            className="border-b border-white/[0.06] px-3 py-2"
                            data-testid={`open-time-${r.callsign}`}
                        >
                            <button
                                className="w-full text-left font-mono-jb text-xs"
                                onClick={() => setOpen(isOpen ? null : r.flight_id)}
                                aria-expanded={isOpen}
                            >
                                <div className="flex items-baseline gap-2">
                                    <span className="t-info">{r.callsign}</span>
                                    <span className="t-sec">
                                        {r.origin}→{r.destination}
                                    </span>
                                    <span className="t-muted">{r.std.slice(11, 16)}Z</span>
                                    <span className={`ml-auto ${severityTone("critical")}`}>
                                        −{r.short_by}
                                    </span>
                                </div>
                                <div className="t-muted mt-0.5">
                                    {r.aircraft_type} ·{" "}
                                    {Object.entries(r.needs)
                                        .map(([rank, n]) => `${n}x ${rank}`)
                                        .join(" ")}
                                </div>
                            </button>

                            {isOpen && (
                                <div className="mt-2 flex flex-col gap-2">
                                    {Object.entries(r.needs).map(([rank, n]) => (
                                        <div key={rank}>
                                            <div className="uppercase-wide t-muted">
                                                {rank} — SHORT {n}
                                            </div>
                                            {(r.candidates[rank] || []).length === 0 && (
                                                <div className="font-mono-jb text-[10px] t-crit">
                                                    No legal {rank} available.
                                                </div>
                                            )}
                                            {(r.candidates[rank] || []).map((c) => (
                                                <button
                                                    key={c.crew_id}
                                                    className="btn w-full text-left mt-1"
                                                    disabled={busy !== null}
                                                    onClick={() => assign(r.flight_id, c.crew_id)}
                                                    data-testid={`assign-open-${r.callsign}-${c.crew_id}`}
                                                >
                                                    {busy === `${r.flight_id}:${c.crew_id}`
                                                        ? "…"
                                                        : `${c.crew_id} ${c.name} · fatigue ${c.fatigue}`}
                                                </button>
                                            ))}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
