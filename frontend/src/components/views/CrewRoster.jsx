import React, { useEffect, useState, useCallback, useMemo } from "react";
import { api } from "../../api";

// Duty-code -> status colour (var) per the design system: colour is signal.
const CODE_VAR = {
    FLT: "var(--status-info)",
    SBY: "var(--status-warning)",
    OFF: "var(--status-nominal)",
    REST: "var(--status-nominal)",
    SICK: "var(--status-critical)",
};

const WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function fmtCol(dateIso) {
    const d = new Date(`${dateIso}T00:00:00Z`);
    return { wd: WEEKDAYS[d.getUTCDay()], dom: d.getUTCDate() };
}

function tint(varName, pct) {
    return `color-mix(in srgb, ${varName} ${pct}%, transparent)`;
}

function Cell({ col, cell, editable, busy, onToggle }) {
    const code = cell.code;
    const varName = code ? CODE_VAR[code] : null;
    const plannedOff = cell.rel === "future" && cell.planned_off;
    const clickable = editable && (col.is_future || col.is_today);

    const style = {};
    if (varName) {
        style.background = tint(varName, col.is_today ? 22 : 14);
        style.color = varName;
    }
    if (col.is_today) style.boxShadow = "inset 0 0 0 1px var(--status-info)";

    const label = code || (clickable ? "+" : "·");

    return (
        <td className="px-1 py-1 text-center border-r border-white/[0.04]">
            <button
                type="button"
                disabled={!clickable || busy}
                onClick={clickable ? () => onToggle(col.day, plannedOff || code === "OFF") : undefined}
                title={
                    clickable
                        ? plannedOff || code === "OFF"
                            ? "Clear day off"
                            : "Roster day off (free of duty)"
                        : undefined
                }
                data-testid={`cell-${cell.day}`}
                className={`w-full min-w-[40px] px-1 py-1 text-[10px] font-mono-jb tracking-wide ${
                    clickable ? "cursor-pointer hover:bg-white/[0.06]" : "cursor-default"
                } ${!varName ? (clickable ? "t-muted" : "t-muted opacity-40") : ""}`}
                style={style}
            >
                {busy ? "…" : label}
            </button>
        </td>
    );
}

export default function CrewRoster({ state, onChanged }) {
    const [roster, setRoster] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filter, setFilter] = useState("ALL");
    const [acFilter, setAcFilter] = useState("ALL");
    const [search, setSearch] = useState("");
    const [busyKey, setBusyKey] = useState(null);

    const load = useCallback(async () => {
        if (!state?.id) return;
        try {
            const r = await api.crewRoster(state.id);
            setRoster(r);
            setError(null);
        } catch (e) {
            setError(e?.message || "failed to load roster");
        } finally {
            setLoading(false);
        }
    }, [state?.id]);

    // Reload when the day rolls, the phase changes, or assignments change.
    useEffect(() => {
        load();
    }, [load, state?.day_number, state?.phase]);

    const canEditToday = state?.phase === "ROSTER";

    const onToggle = useCallback(
        async (crewId, day, currentlyOff) => {
            const key = `${crewId}-${day}`;
            setBusyKey(key);
            try {
                await api.setDayOff(state.id, crewId, day, !currentlyOff);
                await load();
                // today edits change crew status -> refresh the rest of the app
                if (day === roster?.day_number && onChanged) onChanged();
            } finally {
                setBusyKey(null);
            }
        },
        [state?.id, roster?.day_number, load, onChanged]
    );

    const rows = useMemo(() => {
        if (!roster) return [];
        let list = roster.crew;
        if (filter !== "ALL") list = list.filter((c) => c.rank === filter);
        if (acFilter !== "ALL") list = list.filter((c) => (c.qualifications || []).includes(acFilter));
        if (search) {
            const s = search.toLowerCase();
            list = list.filter(
                (c) => c.crew_id.toLowerCase().includes(s) || c.name.toLowerCase().includes(s)
            );
        }
        // Most urgent (closest to a mandatory day off) first, then by id.
        return [...list].sort(
            (a, b) => b.days_since_off - a.days_since_off || (a.crew_id < b.crew_id ? -1 : 1)
        );
    }, [roster, filter, acFilter, search]);

    const summary = useMemo(() => {
        if (!roster) return { atLimit: 0, due: 0 };
        return {
            atLimit: roster.crew.filter((c) => c.at_limit).length,
            due: roster.crew.filter((c) => c.due_off && !c.at_limit).length,
        };
    }, [roster]);

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center t-muted font-mono-jb text-xs" data-testid="crew-roster">
                LOADING ROSTER LINE…
            </div>
        );
    }
    if (error) {
        return (
            <div className="h-full flex items-center justify-center t-crit font-mono-jb text-xs" data-testid="crew-roster">
                ROSTER LOAD FAILED · {error}
            </div>
        );
    }

    const cols = roster.columns;

    return (
        <div className="h-full flex flex-col" data-testid="crew-roster">
            {/* Header */}
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-4">
                <div>
                    <div className="label-key">CREW ROSTER LINE</div>
                    <div className="font-azeret text-lg">DAYS-OFF PLANNING · LHR BASE</div>
                </div>
                <div className="flex-1" />
                <div className="uppercase-wide t-sec">
                    DAY {roster.day_number} · MAX {roster.max_consecutive_duty_days} CONSEC ·{" "}
                    <span className="t-crit">{summary.atLimit}</span> AT LIMIT ·{" "}
                    <span className="t-warn">{summary.due}</span> DUE
                </div>
            </div>

            {/* Controls + legend */}
            <div className="px-4 py-2 border-b border-white/10 flex gap-2 items-center flex-wrap">
                <input
                    data-testid="roster-search-input"
                    placeholder="SEARCH"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                <span className="uppercase-wide t-muted ml-1">RANK</span>
                {["ALL", "CP", "FO", "SC", "CC"].map((r) => (
                    <button
                        key={r}
                        data-testid={`roster-filter-${r}`}
                        className={`btn ${filter === r ? "btn-primary" : ""}`}
                        onClick={() => setFilter(r)}
                    >
                        {r}
                    </button>
                ))}
                <span className="uppercase-wide t-muted ml-2">TYPE</span>
                {["ALL", "A320", "A350", "B777"].map((t) => (
                    <button
                        key={t}
                        data-testid={`roster-actype-${t}`}
                        className={`btn ${acFilter === t ? "btn-primary" : ""}`}
                        onClick={() => setAcFilter(t)}
                        title="Filter crew by type rating"
                    >
                        {t}
                    </button>
                ))}
                <div className="flex-1" />
                <div className="flex items-center gap-3 uppercase-wide t-muted text-[10px]">
                    {["FLT", "SBY", "OFF", "SICK"].map((c) => (
                        <span key={c} className="flex items-center gap-1">
                            <span
                                className="inline-block w-2.5 h-2.5"
                                style={{ background: tint(CODE_VAR[c], 35), boxShadow: `inset 0 0 0 1px ${CODE_VAR[c]}` }}
                            />
                            {c}
                        </span>
                    ))}
                    <span className="t-sec">· CLICK A FUTURE CELL TO TOGGLE OFF</span>
                </div>
            </div>

            {/* Calendar table */}
            <div className="flex-1 scroll-area">
                <table className="text-xs font-mono-jb border-collapse" data-testid="roster-cal-table">
                    <thead className="sticky top-0 bg-[#050505] z-10">
                        <tr className="uppercase-wide t-muted">
                            <th className="text-left px-3 py-2 border-b border-white/10 sticky left-0 bg-[#050505] z-20">CREW</th>
                            <th className="text-left px-2 py-2 border-b border-white/10">RANK</th>
                            <th className="text-right px-2 py-2 border-b border-white/10" title="Consecutive duty days since last day off">CONSEC</th>
                            {cols.map((col) => {
                                const { wd, dom } = fmtCol(col.date);
                                return (
                                    <th
                                        key={col.day}
                                        className={`px-1 py-2 text-center border-b border-white/10 border-r border-white/[0.04] ${
                                            col.is_today ? "t-info" : col.is_future ? "t-sec" : "t-muted"
                                        }`}
                                        style={col.is_today ? { boxShadow: "inset 0 -2px 0 0 var(--status-info)" } : undefined}
                                    >
                                        <div className="text-[9px]">{wd}</div>
                                        <div className="text-[11px]">{dom}</div>
                                        {col.is_today && <div className="text-[8px] t-info">TDY</div>}
                                    </th>
                                );
                            })}
                        </tr>
                    </thead>
                    <tbody className="zebra">
                        {rows.map((c) => {
                            const consecTone = c.at_limit ? "t-crit" : c.due_off ? "t-warn" : "t-muted";
                            return (
                                <tr
                                    key={c.crew_id}
                                    className="border-b border-white/[0.04] hover:bg-white/[0.02]"
                                    data-testid={`roster-row-${c.crew_id}`}
                                >
                                    <td className="px-3 py-1 sticky left-0 bg-[#050505] z-10 whitespace-nowrap">
                                        <span className="t-info">{c.crew_id}</span>{" "}
                                        <span className="t-sec">{c.name}</span>
                                    </td>
                                    <td className="px-2 py-1 t-sec">{c.rank}</td>
                                    <td className={`px-2 py-1 text-right ${consecTone}`}>
                                        {c.days_since_off}
                                        {c.at_limit && <span className="badge t-crit ml-1">REQ</span>}
                                        {c.due_off && !c.at_limit && <span className="badge t-warn ml-1">DUE</span>}
                                    </td>
                                    {c.cells.map((cell, i) => (
                                        <Cell
                                            key={cell.day}
                                            col={cols[i]}
                                            cell={cell}
                                            editable={canEditToday || cols[i].is_future}
                                            busy={busyKey === `${c.crew_id}-${cell.day}`}
                                            onToggle={(day, off) => onToggle(c.crew_id, day, off)}
                                        />
                                    ))}
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
