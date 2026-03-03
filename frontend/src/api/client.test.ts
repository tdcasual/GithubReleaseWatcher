import { describe, it, expect } from "vitest";

import { buildApiPath } from "./client";

describe("client", () => {
  it("uses /api/v2 prefix", () => {
    expect(buildApiPath("/jobs")).toBe("/api/v2/jobs");
  });
});
