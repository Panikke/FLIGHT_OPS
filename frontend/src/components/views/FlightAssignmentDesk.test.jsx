import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import FlightAssignmentDesk from "./FlightAssignmentDesk";

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
