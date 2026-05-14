import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API, timeout: 60000 });

export const api = {
    newGame: (scenario = "free_play") => client.post("/sim/new", { scenario }).then((r) => r.data),
    getState: (gid) => client.get(`/sim/${gid}`).then((r) => r.data),
    rosterStatus: (gid) => client.get(`/sim/${gid}/roster_status`).then((r) => r.data),
    precheck: (gid, fid, crewId) =>
        client.post(`/sim/${gid}/check_assignment/${fid}`, { crew_id: crewId }).then((r) => r.data),
    assign: (gid, fid, crewId, force = false) =>
        client.post(`/sim/${gid}/assign/${fid}`, { crew_id: crewId, force }).then((r) => r.data),
    unassign: (gid, fid, cid) =>
        client.post(`/sim/${gid}/unassign/${fid}/${cid}`).then((r) => r.data),
    startDay: (gid) => client.post(`/sim/${gid}/start_day`).then((r) => r.data),
    tick: (gid, minutes = 30) =>
        client.post(`/sim/${gid}/tick`, { minutes }).then((r) => r.data),
    resolve: (gid, iid, action) =>
        client.post(`/sim/${gid}/resolve/${iid}`, { action }).then((r) => r.data),
    endDay: (gid) => client.post(`/sim/${gid}/end_day`).then((r) => r.data),
    nextDay: (gid) => client.post(`/sim/${gid}/next_day`).then((r) => r.data),
    advisor: (gid, payload = {}) =>
        client.post(`/sim/${gid}/advisor`, payload).then((r) => r.data),
};
