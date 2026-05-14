import React, { useState, useMemo } from "react";

// Short-haul cap (780 min) used as the visual 100% reference
const FDP_CAP_MIN = 780;

function FdpBar({ fdpUsedMin }) {
    const used = fdpUsedMin || 0;
    const pct = Math.min(100, (used / FDP_CAP_MIN) * 100);
    const color =
        pct >= 90 ? "var(--status-critical)" : pct >= 70 ? "var(--status-warning)" : "var(--status-nominal)";
    const label = `${Math.floor(used / 60)}h${(used % 60).toString().padStart(2, "0")}`;
    return (
        <div className="flex items-center gap-2 min-w-[80px]">
            <div className="flex-1 h-1.5 bg-white/10 relative">
                <div
                    style={{ width: `${pct}%`, background: color }}
                    className="absolute top-0 left-0 h-full transition-all"
                />
            </div>
            <span className="font-mono-jb text-[10px] t-sec w-[32px] text-right">{label}</span>
        </div>
    );
}

export default function CrewPanel({ state }) {
    const [filter, setFilter] = useState("ALL");
    const [search, setSearch] = useState("");

    const crew = useMemo(() => {
        let list = state.crew;
        if (filter !== "ALL") list = list.filter((c) => c.rank === filter);
        if (search) {
            const s = search.toLowerCase();
            list = list.filter((c) => c.id.toLowerCase().includes(s) || c.name.toLowerCase().includes(s));
        }
        return list;
    }, [state.crew, filter, search]);

    const counts = {
        total: state.crew.length,
        available: state.crew.filter((c) => c.status === "available").length,
        on_duty: state.crew.filter((c) => c.status === "on_duty").length,
        standby: state.crew.filter((c) => c.status === "standby").length,
        sick: state.crew.filter((c) => c.status === "sick").length,
    };

    return (
        <div className="h-full flex flex-col" data-testid="crew-panel">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-4">
                <div>
                    <div className="label-key">CREW POOL</div>
                    <div className="font-azeret text-lg">PERSONNEL · LHR BASE</div>
                </div>
                <div className="flex-1" />
                <div className="uppercase-wide t-sec">
                    TOTAL {counts.total} · AVL <span className="t-nominal">{counts.available}</span> · DUTY <span className="t-info">{counts.on_duty}</span> · STBY <span className="t-warn">{counts.standby}</span> · SICK <span className="t-crit">{counts.sick}</span>
                </div>
            </div>
            <div className="px-4 py-2 border-b border-white/10 flex gap-2 items-center">
                <input
                    data-testid="crew-search-input"
                    placeholder="SEARCH"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                {["ALL", "CP", "FO", "SC", "CC"].map((r) => (
                    <button
                        key={r}
                        data-testid={`crew-filter-${r}`}
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
                            <th className="text-left px-3 py-2 border-b border-white/10">BASE</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">REST</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">FDP USED</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">28D BLK</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">FATIGUE</th>
                            <th className="text-left px-3 py-2 border-b border-white/10">STAT</th>
                        </tr>
                    </thead>
                    <tbody className="zebra">
                        {crew.map((c) => {
                            const stTone =
                                c.status === "available"
                                    ? "t-nominal"
                                    : c.status === "standby"
                                      ? "t-warn"
                                      : c.status === "sick"
                                        ? "t-crit"
                                        : "t-sec";
                            return (
                                <tr key={c.id} className="border-b border-white/[0.04]" data-testid={`crew-${c.id}`}>
                                    <td className="px-3 py-2 t-info">{c.id}</td>
                                    <td className="px-3 py-2">{c.name}</td>
                                    <td className="px-3 py-2">{c.rank}</td>
                                    <td className="px-3 py-2 t-sec">{c.qualifications.join(",")}</td>
                                    <td className="px-3 py-2 t-sec">{c.base}</td>
                                    <td className="px-3 py-2 t-sec">{c.rest_hr_since_duty.toFixed(0)}h</td>
                                    <td className="px-3 py-2">
                                        <FdpBar fdpUsedMin={c.fdp_used_min} />
                                    </td>
                                    <td className="px-3 py-2 t-sec">{c.block_28d_hr.toFixed(1)}</td>
                                    <td className={`px-3 py-2 ${c.fatigue_score > 70 ? "t-crit" : c.fatigue_score > 45 ? "t-warn" : "t-nominal"}`}>
                                        {c.fatigue_score}
                                    </td>
                                    <td className={`px-3 py-2 ${stTone}`}>{c.status.toUpperCase()}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
