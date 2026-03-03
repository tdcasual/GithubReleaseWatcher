import { buildApiPath } from "./api/client";

const app = document.getElementById("app");
if (app) {
  app.textContent = `GRW V2 frontend scaffold (${buildApiPath("/health")})`;
}
