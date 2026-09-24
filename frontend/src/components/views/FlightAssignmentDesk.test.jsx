import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import FlightAssignmentDesk from "./FlightAssignmentDesk";
import { api } from "../../api";

jest.mock("../../api", () => ({ api: { precheck: jest.fn() } }));

test("shows an empty state when there are no released flights", () => {
    const markup = renderToStaticMarkup(
        <FlightAssignmentDesk
            state={{ id: "empty-game", flights: [], crew: [] }}
            onChanged={() => {}}
            onStartDay={() => {}}
        />
    );

    expect(markup).toContain("No released flights are available for assignment.");
});

test("keeps assignment locked until the latest legality check completes", async () => {
    global.IS_REACT_ACT_ENVIRONMENT = true;
    const pending = {};
    api.precheck.mockImplementation((_game, _flight, crewId) => new Promise((resolve) => {
        pending[crewId] = resolve;
    }));
    const state = {
        id: "test-game",
        phase: "ROSTER",
        flights: [{ id: "FLT-1", pairing_id: "P1", callsign: "EGW1", origin: "LHR",
            destination: "MAD", std: "2026-09-24T10:00:00+00:00", aircraft_reg: "G-EAGA",
            aircraft_type: "A320", block_min: 120, assigned_crew_ids: [],
            required_crew: { CP: 1, FO: 0, SC: 0, CC: 0, type_qual: "A320" } }],
        crew: ["CP1", "CP2"].map((id) => ({ id, rank: "CP", name: id,
            qualifications: ["A320"], status: "available", rest_hr_since_duty: 12,
            fatigue_score: 10 })),
    };
    const host = document.createElement("div");
    const root = createRoot(host);
    try {
        await act(async () => root.render(
            <FlightAssignmentDesk state={state} onChanged={() => {}} onStartDay={() => {}} />
        ));
        const assign = () => host.querySelector('[data-testid="pairing-assign-btn"]');
        await act(async () => host.querySelector('[data-testid="pairing-candidate-CP1"]').click());
        expect(host.textContent).toContain("Checking qualification");
        expect(host.textContent).not.toContain("No legality issues detected");
        expect(assign().disabled).toBe(true);

        await act(async () => host.querySelector('[data-testid="pairing-candidate-CP2"]').click());
        await act(async () => pending.CP1({ warnings: [{ code: "OLD", severity: "critical", message: "Stale result" }] }));
        expect(host.textContent).not.toContain("Stale result");
        expect(assign().disabled).toBe(true);

        await act(async () => pending.CP2({ warnings: [] }));
        expect(host.textContent).toContain("No legality issues detected");
        expect(assign().disabled).toBe(false);
    } finally {
        await act(async () => root.unmount());
        api.precheck.mockReset();
    }
});
