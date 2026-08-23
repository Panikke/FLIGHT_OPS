import React, { useEffect, useState } from "react";
import { api } from "../api";
import { severityTone } from "../lib/status";

// One line per KIND of problem, not per instance. Thirteen crew out of
// position is ONE fact a controller needs to know about, and rendering it as
// thirteen critical lines buried the two open sectors and every live incident
// underneath it. Rolling up keeps the standing-conditions strip from drowning
// the event queue next to it.
const SEVERITY_RANK = { critical: 0, warning: 1, advisory: 2 };

// Group by the CAUSE, not the symptom class. Thirteen out-of-position crew
// across four late inbounds are four problems with four different fixes, not
// one thirteen-deep list — and the player's mental model is pairings, not
// warning codes. Grouping by code made the strip shorter; grouping by pairing
// makes it answerable.
function rollUp(items) {
    const groups = new Map();
    for (const w of items) {
        const key = w.pairing_id || w.flight_id || w.code;
        if (!groups.has(key)) {
            groups.set(key, {
                key,
                code: w.code,
                label: w.pairing_id || w.flight_id || w.code,
                severity: w.severity,
                items: [],
            });
        }
        const g = groups.get(key);
        g.items.push(w);
        // A group is as severe as its worst member, and named for it.
        if (SEVERITY_RANK[w.severity] < SEVERITY_RANK[g.severity]) {
            g.severity = w.severity;
            g.code = w.code;
        }
    }
    return [...groups.values()].sort(
        (a, b) =>
            SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
            b.items.length - a.items.length
    );
}

/**
 * The problem monitor — what is wrong RIGHT NOW by the rules, as opposed to
 * what has happened to the player by chance.
 *
 * Every exception in this game used to arrive as an incident card: an event.
 * Real crew tracking leads with a live irregularities list — open sectors,
 * duties about to bust, crew out of position — because those are conditions,
 * and a controller stares at them all shift. The data already existed in the
 * engine; nothing surfaced it.
 */
export default function ProblemMonitor({ state, onOpenCrew }) {
    const [items, setItems] = useState([]);
    const [suppressed, setSuppressed] = useState(0);
    const [openGroup, setOpenGroup] = useState(null);
    // Collapsible, and it remembers. A persistent strip the player cannot get
    // out of the way is worse than no strip.
    const [collapsed, setCollapsed] = useState(
        () => window.localStorage?.getItem("occ.problemMonitor.collapsed") === "1"
    );

    function toggleCollapsed() {
        setCollapsed((c) => {
            const next = !c;
            try {
                window.localStorage?.setItem("occ.problemMonitor.collapsed", next ? "1" : "0");
            } catch {
                /* private mode — collapse still works for this session */
            }
            return next;
        });
    }

    useEffect(() => {
        let cancelled = false;
        api.irregularities(state.id)
            .then((d) => {
                if (cancelled) return;
                setItems(d.irregularities || []);
                // Held back because an incident already covers them. Shown as
                // a count so nothing is ever silently hidden.
                setSuppressed((d.suppressed || []).length);
            })
            .catch(() => {
                if (!cancelled) {
                    setItems([]);
                    setSuppressed(0);
                }
            });
        return () => {
            cancelled = true;
        };
        // Re-read whenever the operation moves: the clock, the roster, or the
        // incident list changing can all create or clear an irregularity.
    }, [state.id, state.clock, state.phase, state.incidents?.length]);

    if (!items.length) return null;

    const critical = items.filter((i) => i.severity === "critical").length;
    const groups = rollUp(items);
    const attention = items.length - critical;

    return (
        <div className="border-b border-white/10 px-4 py-2" data-testid="problem-monitor">
            <div className="flex items-baseline gap-3">
                <button
                    className="label-key flex items-baseline gap-1.5"
                    onClick={toggleCollapsed}
                    aria-expanded={!collapsed}
                    data-testid="problem-monitor-collapse"
                >
                    <span aria-hidden="true">{collapsed ? "▸" : "▾"}</span>
                    PROBLEM MONITOR
                </button>
                <span className="font-mono-jb text-[10px] t-muted">
                    {critical} BLOCKING · {attention} ATTENTION
                    {suppressed > 0 ? ` · ${suppressed} ON CARDS` : ""}
                </span>
                {collapsed && (
                    <span className="font-mono-jb text-[10px] t-sec">
                        {groups
                            .slice(0, 3)
                            .map((g) =>
                                g.items.length > 1
                                    ? `${g.label} ${g.code} ×${g.items.length}`
                                    : `${g.label} ${g.code}`
                            )
                            .join("  ·  ")}
                    </span>
                )}
                {onOpenCrew && (
                    <button className="btn ml-auto" onClick={onOpenCrew}>
                        ▸ CREW TRACKING
                    </button>
                )}
            </div>
            {!collapsed && (
                <div className="flex flex-col gap-0.5 mt-1.5">
                    {groups.map((g) => {
                        const isOpen = openGroup === g.key;
                        const single = g.items.length === 1;
                        return (
                            <div key={g.key} data-testid={`irregularity-${g.code}`}>
                                <button
                                    className="font-mono-jb text-[10px] flex items-baseline gap-2 text-left w-full"
                                    onClick={() => setOpenGroup(isOpen ? null : g.key)}
                                    aria-expanded={isOpen}
                                >
                                    <span className={`uppercase-wide ${severityTone(g.severity)}`}>
                                        {g.code}
                                    </span>
                                    {g.label !== g.code && (
                                        <span className="t-info">{g.label}</span>
                                    )}
                                    {single ? (
                                        <span className="t-sec">{g.items[0].message}</span>
                                    ) : (
                                        <>
                                            <span className="t-warn">×{g.items.length}</span>
                                            <span className="t-muted">
                                                {isOpen ? "hide" : "show"}
                                            </span>
                                        </>
                                    )}
                                </button>
                                {isOpen && !single && (
                                    <div className="flex flex-col gap-0.5 pl-4 mt-0.5 max-h-40 overflow-y-auto">
                                        {g.items.map((w, idx) => (
                                            // Index is part of the key: two crew
                                            // on one flight share code AND
                                            // flight_id, and the old key
                                            // collided on exactly that case.
                                            <div
                                                key={`${g.key}-${w.crew_id || w.code}-${idx}`}
                                                className="font-mono-jb text-[10px] t-sec"
                                            >
                                                {w.message}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
