import React from "react";
import { severityTone, severityBorder } from "../lib/status";

/**
 * The house legality-warning block: `[SEVERITY] CODE`, the message, the rule
 * reference.
 *
 * This existed as three near-copies — AssignModal, and twice inside
 * AircraftControl — and they had diverged. The compatibility panel hard-coded
 * the critical styling for every warning regardless of severity, so a
 * `warning`-severity item rendered as red inside a red rule, while the ferry
 * panel twenty lines below branched correctly. One component, one rule.
 */
export default function WarningBlock({ warning, testIdPrefix }) {
    return (
        <div
            className={`border-l-2 mb-3 pl-3 py-1 ${severityBorder(warning.severity)}`}
            data-testid={testIdPrefix ? `${testIdPrefix}-${warning.code}` : undefined}
        >
            <div
                className={`font-mono-jb text-xs uppercase tracking-widest ${severityTone(
                    warning.severity
                )}`}
            >
                [{warning.severity.toUpperCase()}] {warning.code}
            </div>
            <div className="mt-1">{warning.message}</div>
            {warning.rule_ref && (
                <div className="uppercase-wide t-muted mt-1">REF: {warning.rule_ref}</div>
            )}
        </div>
    );
}
