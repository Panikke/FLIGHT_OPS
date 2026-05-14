import React, { useMemo } from "react";

function tToPx(iso, dayStart) {
    const ms = new Date(iso).getTime() - new Date(dayStart).getTime();
    return (ms / 60000) * 1.2; // 1.2 px per minute
}

function flightTone(f) {
    if (f.status === "cancelled") return "bg-[var(--status-critical)]/30 border-[var(--status-critical)]";
    if (f.status === "diverted") return "bg-[var(--status-critical)]/30 border-[var(--status-critical)]";
    if (f.delay_min >= 60) return "bg-[var(--status-critical)]/25 border-[var(--status-critical)]";
    if (f.delay_min > 15) return "bg-[var(--status-warning)]/25 border-[var(--status-warning)]";
    return "bg-[var(--status-info)]/15 border-[var(--status-info)]";
}

export default function FlightTimeline({ state }) {
    const dayStart = state.day_start;
    const hours = 24;
    const totalPx = 60 * hours * 1.2; // total width
    const tails = useMemo(() => Array.from(new Set(state.flights.map((f) => f.aircraft_reg))), [state.flights]);

    const clockPx = tToPx(state.clock, dayStart);

    return (
        <div className="h-full flex flex-col" data-testid="flight-timeline">
            <div className="px-4 py-3 border-b border-white/10">
                <div className="label-key">FLIGHT TIMELINE</div>
                <div className="font-azeret text-lg">FLEET ROTATIONS · Z-TIME</div>
            </div>
            <div className="flex-1 scroll-area">
                <div className="relative" style={{ width: totalPx + 140 }}>
                    {/* hour ruler */}
                    <div className="sticky top-0 z-20 flex bg-[#050505] border-b border-white/10">
                        <div className="w-[140px] flex-shrink-0 border-r border-white/10 px-3 py-2 uppercase-wide t-muted">A/C REG</div>
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

                    {tails.map((reg) => {
                        const ac = state.fleet.find((a) => a.reg === reg);
                        const rows = state.flights.filter((f) => f.aircraft_reg === reg).sort((a, b) => (a.std < b.std ? -1 : 1));
                        return (
                            <div key={reg} className="flex border-b border-white/[0.05]" data-testid={`row-tail-${reg}`}>
                                <div className="w-[140px] flex-shrink-0 border-r border-white/10 px-3 py-3 font-mono-jb text-xs">
                                    <div className="t-info">{reg}</div>
                                    <div className="t-muted">{ac?.type}</div>
                                </div>
                                <div className="relative" style={{ width: totalPx, height: 56 }}>
                                    {rows.map((f) => {
                                        const left = tToPx(f.std, dayStart);
                                        const width = Math.max(28, f.block_min * 1.2 + f.delay_min * 1.2);
                                        return (
                                            <div
                                                key={f.id}
                                                className={`absolute top-2 h-10 border-l-2 ${flightTone(f)} px-2 py-1 font-mono-jb text-[11px] overflow-hidden`}
                                                style={{ left, width }}
                                                title={`${f.callsign} ${f.origin}-${f.destination} STD ${f.std.slice(11,16)} status ${f.status} delay ${f.delay_min}`}
                                                data-testid={`block-${f.callsign}`}
                                            >
                                                <div className="leading-tight">
                                                    <span className="t-info">{f.callsign}</span> {f.origin}→{f.destination}
                                                </div>
                                                <div className="t-muted">
                                                    {f.std.slice(11, 16)} {f.delay_min > 0 ? `(+${f.delay_min})` : ""} {f.status === "cancelled" ? "CNX" : ""}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}

                    {/* now line */}
                    <div
                        className="absolute top-0 bottom-0 w-[2px] bg-[var(--status-info)] z-10 pointer-events-none"
                        style={{ left: 140 + clockPx }}
                        data-testid="now-line"
                    />
                </div>
            </div>
        </div>
    );
}
