/**
 * One definition of what a delay LOOKS like, shared by every view.
 *
 * These thresholds used to be copied into RosterBoard, FlightTimeline and
 * AircraftControl independently, and they had drifted: a rotation 90 minutes
 * down read red on the timeline and amber on the aircraft desk. A controller
 * learns the colour once — three dialects across four views teaches them to
 * distrust it and read the text instead, which is exactly the three-second
 * read the desk cannot afford.
 */

// Minutes of delay at which a flight stops being nominal, then stops being
// merely degraded. 15 matches the engine's own on-time definition.
export const DELAY_WARN_MIN = 15;
export const DELAY_CRIT_MIN = 60;

/** Status label + tone for a flight, from its real delay rather than its
 *  status string. Returns {label, tone}. */
export function flightStatus(f) {
    if (f.status === "cancelled") return { label: "CNX", tone: "t-crit" };
    if (f.status === "diverted") return { label: "DIV", tone: "t-crit" };
    if (f.delay_min >= DELAY_CRIT_MIN) return { label: `DLY+${f.delay_min}`, tone: "t-crit" };
    if (f.delay_min > DELAY_WARN_MIN) return { label: `DLY+${f.delay_min}`, tone: "t-warn" };
    if (f.status === "airborne") return { label: "AIR", tone: "t-info" };
    if (f.status === "boarding") return { label: "BRD", tone: "t-info" };
    return { label: "OTP", tone: "t-nominal" };
}

/** Tone alone, for a delay figure in minutes. */
export function delayTone(min) {
    if (min >= DELAY_CRIT_MIN) return "t-crit";
    if (min > DELAY_WARN_MIN) return "t-warn";
    return "t-nominal";
}

/**
 * Severity tone for the house `{code, severity, message, rule_ref}` warning
 * shape. Amber is degraded / attention, red is breach / blocked — never the
 * other way round, and never both for the same severity.
 */
export function severityTone(severity) {
    return severity === "critical" ? "t-crit" : "t-warn";
}

export function severityBorder(severity) {
    return severity === "critical"
        ? "border-[var(--status-critical)]"
        : "border-[var(--status-warning)]";
}
