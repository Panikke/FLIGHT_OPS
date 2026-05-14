import React, { useState } from "react";

export default function AdvisorPanel({ state, busy, onAsk, lastResponse }) {
    const [q, setQ] = useState("");

    function submit(e) {
        e?.preventDefault();
        onAsk(q.trim() || null);
        setQ("");
    }

    const history = state.advisor_history || [];

    return (
        <div className="h-full flex flex-col telex" data-testid="advisor-panel">
            <div className="px-4 py-3 border-b border-white/10 flex items-center gap-3">
                <div>
                    <div className="label-key">OPS-ADVISOR</div>
                    <div className="font-azeret text-lg">AI ADVISORY CHANNEL</div>
                </div>
                <div className="flex-1" />
                <span className="badge t-info" data-testid="advisor-status">
                    {busy ? "QUERYING..." : "ONLINE"}
                </span>
            </div>

            <div className="flex-1 scroll-area p-4 font-mono-jb text-xs">
                {history.length === 0 && !lastResponse && (
                    <div className="t-muted">[SYS] No advisory traffic yet. Ask the desk for tactical guidance.</div>
                )}
                {history.map((h, i) => (
                    <div key={i} className="mb-5 border-l-2 border-white/10 pl-3">
                        <div className="uppercase-wide t-muted">
                            {h.ts.slice(11, 19)}Z · {h.incident_id ? `RE: ${h.incident_id}` : "GENERAL"}
                        </div>
                        <div className="t-sec mt-1">&gt;&gt; YOU: {h.question.slice(0, 200)}</div>
                        <div className="t-info mt-1 whitespace-pre-wrap">&gt;&gt; SYS_MSG: {h.response}</div>
                    </div>
                ))}
                {lastResponse && history.length === 0 && (
                    <div className="t-info whitespace-pre-wrap">&gt;&gt; SYS_MSG: {lastResponse}</div>
                )}
            </div>

            <form onSubmit={submit} className="border-t border-white/10 p-3 flex gap-2 mb-12">
                <input
                    data-testid="advisor-input"
                    className="flex-1"
                    placeholder="ASK THE DESK..."
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    disabled={busy}
                />
                <button data-testid="advisor-send-btn" className="btn btn-primary" type="submit" disabled={busy}>
                    SEND
                </button>
            </form>
        </div>
    );
}
