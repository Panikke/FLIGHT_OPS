import React from "react";

const RULES = [
    {
        code: "ORO.FTL.205",
        title: "Maximum Daily Flight Duty Period (FDP)",
        plain:
            "An FDP is the total time from report-on to engines-off-on-the-last-sector. Acclimatised, 2-sector short-haul caps at 13h; long-haul ULR caps lower depending on rest facility and crew complement. We add ~90 min for report + post-flight.",
    },
    {
        code: "ORO.FTL.210",
        title: "28-Day and Annual Block Hour Limits",
        plain:
            "100 block hours in any 28 consecutive days. 1000 in 12 months. Cumulative fatigue trumps a tidy roster.",
    },
    {
        code: "ORO.FTL.235",
        title: "Minimum Rest",
        plain:
            "Minimum 12h rest at home base, 10h away from base, before the next reporting time. The clock starts when the previous duty ends.",
    },
    {
        code: "ORO.FTL.225",
        title: "Standby & Reserve",
        plain:
            "Airport standby counts toward FDP. Home standby counts after the 6th hour. Use standby callouts carefully: a 5-hour wait then a long-haul leg eats FDP fast.",
    },
    {
        code: "EASA FCL.740",
        title: "Type Rating Validity",
        plain:
            "A pilot may operate only the type(s) on which they are currently rated and recent. Mixing an A350 captain onto a B777 sector is a hard no.",
    },
    {
        code: "ORO.FTL.120",
        title: "Fatigue Risk Management (FRM)",
        plain:
            "Fatigue is a leading causal factor in incidents. High fatigue scores call for mitigation: split duty, augmented crew, route swap, or extra rest.",
    },
    {
        code: "MED.A.020",
        title: "Fitness to Fly",
        plain:
            "A crew member who self-declares sick is unfit to operate. They cannot be coerced or overridden — the duty is reassigned.",
    },
    {
        code: "DISCRETION",
        title: "Commander's Discretion",
        plain:
            "The captain may extend FDP within strict limits in unforeseen circumstances. This is a safety valve, not a planning tool. In this sim, we charge a fatigue penalty and report it.",
    },
];

export default function RegsHelp() {
    return (
        <div className="h-full flex flex-col" data-testid="regs-help">
            <div className="px-4 py-3 border-b border-white/10">
                <div className="label-key">REFERENCE</div>
                <div className="font-azeret text-lg">EASA / UK CAA FTL · OPERATIONAL CHEAT SHEET</div>
                <div className="uppercase-wide t-warn mt-1">
                    SIMULATION ONLY · NOT AN OFFICIAL COMPLIANCE DOCUMENT
                </div>
            </div>
            <div className="flex-1 scroll-area p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                {RULES.map((r) => (
                    <div key={r.code} className="panel p-4" data-testid={`regs-${r.code.replace(/[^A-Za-z0-9]/g, "_")}`}>
                        <div className="uppercase-wide t-info">{r.code}</div>
                        <div className="font-azeret text-base mt-1">{r.title}</div>
                        <div className="mt-2 t-sec">{r.plain}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}
