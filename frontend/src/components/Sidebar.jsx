import React from "react";

const NAV = [
    { id: "roster", label: "ROSTER" },
    { id: "aircraft", label: "AIRCRAFT" },
    { id: "timeline", label: "TIMELINE" },
    { id: "incidents", label: "INCIDENTS" },
    { id: "crew", label: "CREW" },
    { id: "calendar", label: "DAYS OFF" },
    { id: "advisor", label: "OPS ADVISOR" },
    { id: "regs", label: "FTL REGS" },
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
                            <span>{n.label}</span>
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
