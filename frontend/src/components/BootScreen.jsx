import React, { useEffect, useState } from "react";

const LOG_LINES = [
    "[OK] EGW OCC TERMINAL v0.9.4 :: warm boot",
    "[OK] Loading FTL ruleset (EASA ORO.FTL.205, 210, 235)",
    "[OK] Aircraft fleet manifest (8 ac) ........... LOADED",
    "[OK] Crew roster pool (114 crew) ............. LOADED",
    "[OK] Standby pool initialised",
    "[OK] OPS-ADVISOR LLM channel ................. ONLINE",
    "[OK] Day-of-Ops weather feed (sim) ........... NOMINAL",
    "[WAIT] Awaiting Crew Controller input >>",
];

export default function BootScreen({ onContinue, loading }) {
    const [shown, setShown] = useState(0);
    useEffect(() => {
        if (shown >= LOG_LINES.length) return;
        const t = setTimeout(() => setShown((s) => s + 1), 140);
        return () => clearTimeout(t);
    }, [shown]);

    return (
        <div
            className="relative h-full w-full flex flex-col"
            data-testid="boot-screen"
            style={{
                backgroundImage:
                    "linear-gradient(rgba(0,0,0,0.86), rgba(0,0,0,0.92)), url(https://images.unsplash.com/photo-1757031299897-8014e806a3fb?crop=entropy&cs=srgb&fm=jpg&q=70)",
                backgroundSize: "cover",
                backgroundPosition: "center",
            }}
        >
            <div className="border-b border-white/10 px-6 py-3 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <div className="kpi-num text-xl t-info">EGW//OCC</div>
                    <div className="uppercase-wide">Eaglewing Operations Control</div>
                </div>
                <div className="uppercase-wide">SIM-MODE :: NOT FOR OPERATIONAL USE</div>
            </div>

            <div className="flex-1 flex items-center justify-center px-6">
                <div className="w-full max-w-3xl">
                    <div className="font-azeret text-[10vw] leading-none tracking-tighter t-info">
                        OCC
                    </div>
                    <div className="font-azeret text-3xl mt-2">
                        CREW · CONTROL · SIM
                    </div>
                    <div className="t-sec mt-3 max-w-xl">
                        A hardcore, mixed-fleet airline operations-control
                        simulation. Plan the roster, then survive a day of
                        sickness, weather, tech, and ATC flow as the duty Crew
                        Controller. EASA / UK CAA-inspired rule checks. This is
                        a simulation, not an official compliance tool.
                    </div>

                    <div className="mt-8 border border-white/10 bg-black/50 p-4 font-mono-jb text-xs t-sec h-[180px] overflow-hidden">
                        {LOG_LINES.slice(0, shown).map((line, i) => (
                            <div
                                key={i}
                                className={
                                    line.startsWith("[OK]")
                                        ? "t-nominal"
                                        : line.startsWith("[WAIT]")
                                          ? "t-warn"
                                          : ""
                                }
                            >
                                {line}
                            </div>
                        ))}
                        {shown < LOG_LINES.length && <div className="cursor-blink t-info" />}
                    </div>

                    <div className="mt-6 flex items-center gap-3">
                        <button
                            data-testid="boot-start-btn"
                            className="btn btn-primary"
                            onClick={onContinue}
                            disabled={loading}
                        >
                            {loading ? "INITIALISING..." : ">> START DUTY"}
                        </button>
                        <div className="uppercase-wide">
                            press start to spin up day 1
                        </div>
                    </div>
                </div>
            </div>

            <div className="border-t border-white/10 px-6 py-2 flex justify-between uppercase-wide">
                <span>BUILD 26.05 :: SIMULATION</span>
                <span>HUB LHR :: FLEET 8 :: CREW 114</span>
            </div>
        </div>
    );
}
