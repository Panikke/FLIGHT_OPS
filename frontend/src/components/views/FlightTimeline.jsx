import React, { useMemo, useState } from "react";

function tToPx(iso, dayStart) {
    const ms = new Date(iso).getTime() - new Date(dayStart).getTime();
    return (ms / 60000) * 1.2; // 1.2 px per minute
}

function flightTone(f) {
    if (f.status === "cancelled") return "bg-[var(--status-critical)]/30 border-[var(--status-critical)]";
    if (f.status === "diverted") return "bg-[var(--status-critical)]/30 border-[var(--status-critical)]";
    if (f.status === "landed") return "bg-white/5 border-white/20";
    if (f.delay_min >= 60) return "bg-[var(--status-critical)]/25 border-[var(--status-critical)]";
    if (f.delay_min > 15) return "bg-[var(--status-warning)]/25 border-[var(--status-warning)]";
    if (f.status === "airborne") return "bg-[var(--status-nominal)]/15 border-[var(--status-nominal)]";
    if (f.status === "boarding") return "bg-[var(--status-info)]/25 border-[var(--status-info)]";
    return "bg-[var(--status-info)]/15 border-[var(--status-info)]";
}

function statusLabel(f) {
    if (f.status === "cancelled") return "CNX";
    if (f.status === "diverted") return "DIV";
    if (f.status === "landed") return "LND";
    if (f.status === "airborne") return "AIR";
    if (f.status === "boarding") return "BRD";
    if (f.delay_min > 0) return `+${f.delay_min}`;
    return "";
}

const RANK_TONE = { CP: "t-warn", FO: "t-info", SC: "t-nominal", CC: "t-sec" };
const RANK_BG = {
    CP: "bg-[var(--status-warning)]/20 border-[var(--status-warning)]",
    FO: "bg-[var(--status-info)]/20 border-[var(--status-info)]",
    SC: "bg-[var(--status-nominal)]/15 border-[var(--status-nominal)]",
    CC: "bg-white/8 border-white/20",
};

export default function FlightTimeline({ state }) {
    const [mode, setMode] = useState("aircraft"); // "aircraft" | "crew"
    const [rankFilter, setRankFilter] = useState("ALL");

    const dayStart = state.day_start;
    const hours = 24;
    const totalPx = 60 * hours * 1.2;
    const tails = useMemo(
        () => Array.from(new Set(state.flights.map((f) => f.aircraft_reg))),
        [state.flights],
    );
    const clockPx = tToPx(state.clock, dayStart);

    // Build crew rows: each crew member who has ≥1 assigned flight
    const crewRows = useMemo(() => {
        const map = new Map(); // crew_id → { crew, flights[] }
        state.flights.forEach((f) => {
            f.assigned_crew_ids.forEach((cid) => {
                const c = state.crew.find((x) => x.id === cid);
                if (!c) return;
                if (!map.has(cid)) map.set(cid, { crew: c, flights: [] });
                map.get(cid).flights.push(f);
            });
        });
        let rows = Array.from(map.values());
        if (rankFilter !== "ALL") rows = rows.filter((r) => r.crew.rank === rankFilter);
        rows.sort((a, b) => {
            const rankOrder = { CP: 0, FO: 1, SC: 2, CC: 3 };
            const ro = (rankOrder[a.crew.rank] ?? 9) - (rankOrder[b.crew.rank] ?? 9);
            if (ro !== 0) return ro;
            return a.crew.id.localeCompare(b.crew.id);
        });
        return rows;
    }, [state.flights, state.crew, rankFilter]);

    const HourRuler = () => (
        <div className="sticky top-0 z-20 flex bg-[#050505] border-b border-white/10">
            <div className="w-[180px] flex-shrink-0 border-r border-white/10 px-3 py-2 uppercase-wide t-muted">
                {mode === "aircraft" ? "A/C REG" : "CREW"}
            </div>
            <div className="relative" style={{ width: totalPx }}>
                {Array.from({ length: hours + 1 }).map((_, h) => (
                    <div
                        key={h}
                        className="absolute top-0 bottom-0 border-l border-white/[0.06] uppercase-wide t-muted px-1"
                        style={{ left: h * 60 * 1.2 }}
                    >
                        {h.toString().padStart(2, "0")}:00
                    </div>
                ))}
                <div className="h-7" />
            </div>
        </div>
    );

    return (
        <div className="h-full flex flex-col" data-testid="flight-timeline">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">FLIGHT TIMELINE</div>
                    <div className="font-azeret text-lg">
                        {mode === "aircraft" ? "FLEET ROTATIONS · Z-TIME" : "CREW DUTY BANDS · Z-TIME"}
                    </div>
                </div>
                <div className="flex-1" />
                <div className="flex border border-white/20">
                    {[
                        { id: "aircraft", label: "AIRCRAFT" },
                        { id: "crew", label: "CREW" },
                    ].map((m) => (
                        <button
                            key={m.id}
                            data-testid={`timeline-mode-${m.id}`}
                            onClick={() => setMode(m.id)}
                            className={`font-mono-jb text-[11px] tracking-widest uppercase px-4 py-2 border-r border-white/10 last:border-r-0 ${
                                mode === m.id
                                    ? "bg-[var(--status-info)] text-black"
                                    : "t-sec hover:bg-white/5"
                            }`}
                        >
                            {m.label}
                        </button>
                    ))}
                </div>
                {mode === "crew" && (
                    <div className="flex gap-1">
                        {["ALL", "CP", "FO", "SC", "CC"].map((r) => (
                            <button
                                key={r}
                                data-testid={`crew-rank-filter-${r}`}
                                className={`btn !py-1 !px-2 ${rankFilter === r ? "btn-primary" : ""}`}
                                onClick={() => setRankFilter(r)}
                            >
                                {r}
                            </button>
                        ))}
                    </div>
                )}
            </div>

            <div className="flex-1 scroll-area">
                {mode === "aircraft" ? (
                    <div className="relative" style={{ width: totalPx + 180 }}>
                        <HourRuler />
                        {tails.map((reg) => {
                            const ac = state.fleet.find((a) => a.reg === reg);
                            const rows = state.flights
                                .filter((f) => f.aircraft_reg === reg)
                                .sort((a, b) => (a.std < b.std ? -1 : 1));
                            return (
                                <div key={reg} className="flex border-b border-white/[0.05]" data-testid={`row-tail-${reg}`}>
                                    <div className="w-[180px] flex-shrink-0 border-r border-white/10 px-3 py-3 font-mono-jb text-xs">
                                        <div className="t-info">{reg}</div>
                                        <div className="t-muted">{ac?.type}</div>
                                    </div>
                                    <div className="relative" style={{ width: totalPx, height: 56 }}>
                                        {rows.map((f) => {
                                            const delay = f.delay_min || 0;
                                            const left = tToPx(f.std, dayStart);
                                            const width = Math.max(28, (f.block_min + delay) * 1.2);
                                            const lbl = statusLabel(f);
                                            return (
                                                <div
                                                    key={f.id}
                                                    className={`absolute top-2 h-10 border-l-2 ${flightTone(f)} px-2 py-1 font-mono-jb text-[11px] overflow-hidden`}
                                                    style={{ left, width }}
                                                    title={`${f.callsign} ${f.origin}-${f.destination} STD ${f.std.slice(11, 16)} status=${f.status} dly=${delay}${f.reactionary_min ? ` (knock-on ${f.reactionary_min}m: ${f.note || "inbound late"})` : ""}`}
                                                    data-testid={`block-${f.callsign}`}
                                                >
                                                    <div className="leading-tight flex items-center gap-1">
                                                        <span className="t-info">{f.callsign}</span>
                                                        <span>{f.origin}→{f.destination}</span>
                                                        {lbl && <span className="t-warn">{lbl}</span>}
                                                    </div>
                                                    <div className="t-muted">
                                                        {f.std.slice(11, 16)}{delay > 0 ? ` (+${delay})` : ""}
                                                        {f.reactionary_min > 0 && (
                                                            <span className="t-warn" title="Knock-on delay from late inbound"> ·R{f.reactionary_min}</span>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}
                        <div
                            className="absolute top-0 bottom-0 w-[2px] bg-[var(--status-info)] z-10 pointer-events-none"
                            style={{ left: 180 + clockPx }}
                            data-testid="now-line"
                        />
                    </div>
                ) : (
                    <div className="relative" style={{ width: totalPx + 180 }}>
                        <HourRuler />
                        {crewRows.length === 0 && (
                            <div className="px-6 py-8 t-muted font-mono-jb text-xs">
                                [SYS] No crew assigned yet — roster flights first.
                            </div>
                        )}
                        {crewRows.map(({ crew: c, flights: cFlights }) => {
                            const sortedFlights = [...cFlights].sort((a, b) => (a.std < b.std ? -1 : 1));
                            // FDP span: report time (first STD - 60 min) to last STA
                            const firstStd = sortedFlights[0]?.std;
                            const lastSta = sortedFlights[sortedFlights.length - 1]?.sta;
                            const fdpStart = firstStd
                                ? new Date(new Date(firstStd).getTime() - 60 * 60000).toISOString()
                                : null;
                            const fdpLeft = fdpStart ? tToPx(fdpStart, dayStart) : null;
                            const fdpWidth = fdpStart && lastSta
                                ? tToPx(lastSta, dayStart) - fdpLeft
                                : 0;

                            return (
                                <div key={c.id} className="flex border-b border-white/[0.05]" data-testid={`crew-row-${c.id}`}>
                                    <div className="w-[180px] flex-shrink-0 border-r border-white/10 px-3 py-2 font-mono-jb text-xs">
                                        <div className={RANK_TONE[c.rank] || "t-sec"}>
                                            {c.rank} · {c.id}
                                        </div>
                                        <div className="t-muted truncate" title={c.name}>{c.name}</div>
                                        <div className="uppercase-wide t-muted">FAT {c.fatigue_score}</div>
                                    </div>
                                    <div className="relative" style={{ width: totalPx, height: 64 }}>
                                        {/* FDP envelope */}
                                        {fdpLeft !== null && fdpWidth > 0 && (
                                            <div
                                                className="absolute top-1 h-14 border border-dashed border-white/10 bg-white/[0.02]"
                                                style={{ left: fdpLeft, width: Math.max(0, fdpWidth) }}
                                                title={`FDP envelope: ${fdpStart?.slice(11,16)} → ${lastSta?.slice(11,16)}`}
                                            />
                                        )}
                                        {/* Flight blocks */}
                                        {sortedFlights.map((f) => {
                                            const delay = f.delay_min || 0;
                                            const left = tToPx(f.std, dayStart);
                                            const width = Math.max(22, (f.block_min + delay) * 1.2);
                                            return (
                                                <div
                                                    key={f.id}
                                                    className={`absolute top-3 h-8 border-l-2 ${RANK_BG[c.rank] || "bg-white/10 border-white/30"} px-1 font-mono-jb text-[10px] overflow-hidden`}
                                                    style={{ left, width }}
                                                    title={`${f.callsign} ${f.origin}→${f.destination} ${f.std.slice(11,16)}Z`}
                                                >
                                                    <div className="leading-tight">
                                                        <span className="font-semibold">{f.callsign}</span>
                                                    </div>
                                                    <div className="t-muted">{f.origin}→{f.destination}</div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}
                        <div
                            className="absolute top-0 bottom-0 w-[2px] bg-[var(--status-info)] z-10 pointer-events-none"
                            style={{ left: 180 + clockPx }}
                            data-testid="now-line"
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
