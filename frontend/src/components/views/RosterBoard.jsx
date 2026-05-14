import React, { useMemo, useState } from "react";

function fmtClock(iso) {
    if (!iso) return "--:--";
    return iso.slice(11, 16);
}

function flightStatus(f) {
    if (f.status === "cancelled") return { label: "CNX", tone: "t-crit" };
    if (f.status === "diverted") return { label: "DIV", tone: "t-crit" };
    if (f.delay_min >= 60) return { label: `DLY+${f.delay_min}`, tone: "t-crit" };
    if (f.delay_min > 15) return { label: `DLY+${f.delay_min}`, tone: "t-warn" };
    if (f.status === "airborne") return { label: "AIR", tone: "t-info" };
    if (f.status === "boarding") return { label: "BRD", tone: "t-info" };
    return { label: "OTP", tone: "t-nominal" };
}

export default function RosterBoard({ state, onOpenAssign, onStartDay, onUnassign }) {
    const [filter, setFilter] = useState("ALL");
    const flights = useMemo(() => {
        let list = [...state.flights].sort((a, b) => (a.std < b.std ? -1 : 1));
        if (filter !== "ALL") list = list.filter((f) => f.aircraft_type === filter);
        return list;
    }, [state.flights, filter]);

    const allComplete = state.flights.every((f) => {
        const req = f.required_crew;
        const total = req.CP + req.FO + req.SC + req.CC;
        return f.assigned_crew_ids.length >= total;
    });

    const incomplete = state.flights.filter((f) => {
        const req = f.required_crew;
        const total = req.CP + req.FO + req.SC + req.CC;
        return f.assigned_crew_ids.length < total;
    }).length;

    return (
        <div className="h-full flex flex-col" data-testid="roster-board">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">ROSTER BOARD</div>
                    <div className="font-azeret text-lg">FLIGHT-LEVEL CREW PAIRING</div>
                </div>
                <div className="flex-1" />
                <div className="uppercase-wide t-sec">FILTER</div>
                {["ALL", "A320", "A350", "B777"].map((t) => (
                    <button
                        key={t}
                        data-testid={`filter-${t}`}
                        className={`btn ${filter === t ? "btn-primary" : ""}`}
                        onClick={() => setFilter(t)}
                    >
                        {t}
                    </button>
                ))}
                <div className="uppercase-wide t-sec ml-4">
                    INCOMPLETE: <span className="t-warn">{incomplete}</span>/{state.flights.length}
                </div>
                {state.phase === "ROSTER" && (
                    <button
                        data-testid="start-day-btn"
                        className={`btn ${allComplete ? "btn-ok" : "btn-warn"} ml-4`}
                        onClick={onStartDay}
                    >
                        {allComplete ? "▶ START DAY" : "▶ START DAY (gaps remain)"}
                    </button>
                )}
            </div>

            <div className="flex-1 scroll-area">
                <table className="w-full text-xs" data-testid="roster-table">
                    <thead className="sticky top-0 bg-[#050505] z-10">
                        <tr className="uppercase-wide t-muted">
                            <th className="text-left px-3 py-2 border-b border-white/10">FLT</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">ROUTE</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STD</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">A/C</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">BLK</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">PAX</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">CREW REQUIRED</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">CREW ASSIGNED</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STAT</th>
                            <th className="text-right px-3 py-2 border-b border-white/10">ACT</th>
                        </tr>
                    </thead>
                    <tbody className="zebra font-mono-jb">
                        {flights.map((f) => {
                            const st = flightStatus(f);
                            const req = f.required_crew;
                            const need = req.CP + req.FO + req.SC + req.CC;
                            const have = f.assigned_crew_ids.length;
                            const assignedByRank = { CP: 0, FO: 0, SC: 0, CC: 0 };
                            f.assigned_crew_ids.forEach((cid) => {
                                const c = state.crew.find((x) => x.id === cid);
                                if (c) assignedByRank[c.rank]++;
                            });
                            return (
                                <tr
                                    key={f.id}
                                    className="border-b border-white/[0.04] hover:bg-white/[0.03]"
                                    data-testid={`row-${f.callsign}`}
                                >
                                    <td className="px-3 py-2 t-info">{f.callsign}</td>
                                    <td className="px-3 py-2">
                                        {f.origin} → {f.destination}
                                    </td>
                                    <td className="px-3 py-2 t-sec">{fmtClock(f.std)}</td>
                                    <td className="px-3 py-2">
                                        {f.aircraft_type} <span className="t-muted">{f.aircraft_reg}</span>
                                    </td>
                                    <td className="px-3 py-2 t-sec">
                                        {Math.floor(f.block_min / 60)}h{(f.block_min % 60).toString().padStart(2, "0")}
                                    </td>
                                    <td className="px-3 py-2 t-sec">{f.pax_count}</td>
                                    <td className="px-3 py-2 t-sec">
                                        CP{req.CP} FO{req.FO} SC{req.SC} CC{req.CC}
                                    </td>
                                    <td className="px-3 py-2">
                                        <span className={have >= need ? "t-nominal" : "t-warn"}>
                                            {have}/{need}
                                        </span>
                                        <span className="t-muted ml-2">
                                            (CP{assignedByRank.CP} FO{assignedByRank.FO} SC{assignedByRank.SC} CC{assignedByRank.CC})
                                        </span>
                                    </td>
                                    <td className={`px-3 py-2 ${st.tone}`}>{st.label}</td>
                                    <td className="px-3 py-2 text-right">
                                        <button
                                            data-testid={`assign-${f.callsign}-btn`}
                                            className="btn btn-primary"
                                            onClick={() => onOpenAssign(f)}
                                        >
                                            ASSIGN
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
