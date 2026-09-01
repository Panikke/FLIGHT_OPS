import React, { useMemo } from "react";

// How many edges to show. A controller wants the last few knock-ons, not a
// history — the debrief is where the full ledger belongs.
const MAX_EDGES = 6;

const TRIGGER_LABEL = {
    tick: "OPERATION",
    ferry: "YOUR FERRY",
    reset_to_zero: "YOUR RESET",
    aircraft_change: "YOUR TAIL SWAP",
};

function triggerLabel(trigger) {
    if (TRIGGER_LABEL[trigger]) return TRIGGER_LABEL[trigger];
    if (trigger?.startsWith("incident_")) {
        return `YOUR ${trigger.slice("incident_".length).replace(/_/g, " ").toUpperCase()}`;
    }
    return "OPERATION";
}

/**
 * Live attribution for reactionary delay.
 *
 * The engine has always known which inbound made which outbound late; without
 * this the player only ever saw the resulting minute count and experienced
 * knock-on delay as weather rather than as the consequence of a decision.
 * Edges caused by something the player did are called out as theirs.
 */
export default function CascadeStrip({ state }) {
    const edges = useMemo(() => {
        const log = state?.cascade_log || [];
        return log.slice(-MAX_EDGES).reverse();
    }, [state?.cascade_log]);

    if (!edges.length) return null;

    const totalMin = (state.cascade_log || []).reduce((sum, e) => sum + (e.added_min || 0), 0);

    return (
        <div className="border-b border-white/10 px-4 py-2" data-testid="cascade-strip">
            <div className="flex items-baseline gap-3 mb-1.5">
                <span className="label-key">CASCADE</span>
                <span className="font-mono-jb text-[10px] t-muted">
                    IATA 93 · REACTIONARY · {totalMin}m TOTAL TODAY
                </span>
            </div>
            <div className="flex flex-wrap gap-x-5 gap-y-1">
                {edges.map((e, idx) => {
                    const mine = e.trigger && e.trigger !== "tick";
                    return (
                        <div
                            key={`${e.flight_id}-${e.ts}-${idx}`}
                            className="font-mono-jb text-[10px] flex items-center gap-1.5"
                            data-testid={`cascade-edge-${e.callsign}`}
                        >
                            <span className="t-crit">{e.callsign}</span>
                            <span className="t-warn">+{e.added_min}m</span>
                            {e.inbound_callsign && (
                                <>
                                    <span className="t-muted">←</span>
                                    <span className="t-sec">
                                        {e.inbound_callsign} {e.kind === "crew" ? "CREW" : "LATE"}
                                    </span>
                                </>
                            )}
                            {mine && (
                                <span className="t-warn uppercase-wide">[{triggerLabel(e.trigger)}]</span>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
