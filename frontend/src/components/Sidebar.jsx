import React from "react";

export const NAV = [
    { id: "roster", label: "ROSTER", key: "1" },
    { id: "aircraft", label: "AIRCRAFT", key: "2" },
    { id: "timeline", label: "TIMELINE", key: "3" },
    { id: "incidents", label: "INCIDENTS", key: "4" },
    { id: "crew", label: "CREW", key: "5" },
    { id: "disposition", label: "DISPOSITION", key: "9" },
    { id: "calendar", label: "DAYS OFF", key: "6" },
    { id: "advisor", label: "OPS ADVISOR", key: "7" },
    { id: "regs", label: "FTL REGS", key: "8" },
];

export default function Sidebar({ active, onSelect, state, openIncidentCount, rosterIncomplete, onExitToMenu }) {
    return (
        <div className="panel-flush w-[180px] flex flex-col">
            <div className="px-3 py-3 border-b border-white/10">
                <div className="label-key">NAVIGATION</div>
            </div>
            <nav className="flex-1">
                {NAV.map((n) => {
                    const isActive = active === n.id;
                    let badge = null;
                    if (n.id === "incidents" && openIncidentCount > 0) {
                        badge = (
                            <span className="badge t-crit ml-2" data-testid={`badge-${n.id}`}>
                                {openIncidentCount}
                            </span>
                        );
                    }
                    if (n.id === "roster" && rosterIncomplete > 0 && state?.phase === "ROSTER") {
                        badge = (
                            <span className="badge t-warn ml-2" data-testid={`badge-${n.id}`}>
                                {rosterIncomplete}
                            </span>
                        );
                    }
                    return (
                        <button
                            key={n.id}
                            data-testid={`nav-${n.id}`}
                            onClick={() => onSelect(n.id)}
                            className={`w-full text-left px-4 py-3 border-b border-white/5 font-mono-jb text-xs tracking-widest uppercase flex items-center justify-between ${
                                isActive
                                    ? "bg-white/5 t-info border-l-2 border-l-[var(--status-info)]"
                                    : "t-sec hover:bg-white/[0.03] hover:text-white"
                            }`}
                        >
                            <span>
                                {n.label}
                                {n.key && (
                                    <span className="t-muted ml-2 normal-case" aria-hidden="true">
                                        {n.key}
                                    </span>
                                )}
                            </span>
                            {badge}
                        </button>
                    );
                })}
            </nav>
            <div className="px-3 py-3 border-t border-white/10 uppercase-wide">
                <div className="t-muted">PHASE</div>
                <div className="t-info text-sm font-azeret mt-1">{state?.phase || "—"}</div>
                <div className="t-muted mt-2">GAME</div>
                <div className="font-mono-jb text-[10px] mt-1">{state?.id || "—"}</div>
                <button
                    data-testid="exit-to-menu-btn"
                    className="btn btn-warn w-full mt-3"
                    onClick={onExitToMenu}
                    title="Return to main menu (current campaign saved)"
                >
                    ↺ EXIT TO MENU
                </button>
            </div>
        </div>
    );
}
