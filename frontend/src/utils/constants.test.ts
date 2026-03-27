import { describe, it, expect } from "vitest";
import {
  COLUMN_NAMES,
  COLUMN_LABELS,
  COLUMN_COLORS,
  PRIORITY_COLORS,
  PRIORITY_LABELS,
  PRIORITY_ORDER,
  HUMAN_GATE_COLUMNS,
  WS_EVENTS,
  API_ROUTES,
} from "./constants";

describe("COLUMN_NAMES", () => {
  it("contains 8 columns in correct order", () => {
    expect(COLUMN_NAMES).toHaveLength(8);
    expect(COLUMN_NAMES[0]).toBe("backlog");
    expect(COLUMN_NAMES[7]).toBe("production");
  });

  it("includes all required columns", () => {
    expect(COLUMN_NAMES).toContain("ai_planning");
    expect(COLUMN_NAMES).toContain("plan_review");
    expect(COLUMN_NAMES).toContain("ai_coding");
    expect(COLUMN_NAMES).toContain("code_review");
    expect(COLUMN_NAMES).toContain("staging");
    expect(COLUMN_NAMES).toContain("staging_verification");
  });
});

describe("COLUMN_LABELS", () => {
  it("has a label for every column", () => {
    for (const col of COLUMN_NAMES) {
      expect(COLUMN_LABELS[col]).toBeDefined();
      expect(COLUMN_LABELS[col].length).toBeGreaterThan(0);
    }
  });
});

describe("COLUMN_COLORS", () => {
  it("has a color for every column", () => {
    for (const col of COLUMN_NAMES) {
      expect(COLUMN_COLORS[col]).toBeDefined();
      expect(COLUMN_COLORS[col]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});

describe("PRIORITY_COLORS", () => {
  it("has CSS classes for all priorities", () => {
    const priorities = ["P0", "P1", "P2", "P3"] as const;
    for (const p of priorities) {
      expect(PRIORITY_COLORS[p]).toBeDefined();
      expect(PRIORITY_COLORS[p]).toContain("bg-");
    }
  });
});

describe("PRIORITY_LABELS", () => {
  it("has labels for all priorities", () => {
    expect(PRIORITY_LABELS["P0"]).toContain("Critical");
    expect(PRIORITY_LABELS["P1"]).toContain("High");
    expect(PRIORITY_LABELS["P2"]).toContain("Medium");
    expect(PRIORITY_LABELS["P3"]).toContain("Low");
  });
});

describe("PRIORITY_ORDER", () => {
  it("P0 is highest priority (lowest number)", () => {
    expect(PRIORITY_ORDER["P0"]).toBeLessThan(PRIORITY_ORDER["P3"]);
  });

  it("priorities are ordered correctly", () => {
    expect(PRIORITY_ORDER["P0"]).toBe(0);
    expect(PRIORITY_ORDER["P1"]).toBe(1);
    expect(PRIORITY_ORDER["P2"]).toBe(2);
    expect(PRIORITY_ORDER["P3"]).toBe(3);
  });
});

describe("HUMAN_GATE_COLUMNS", () => {
  it("includes plan_review and code_review", () => {
    expect(HUMAN_GATE_COLUMNS).toContain("plan_review");
    expect(HUMAN_GATE_COLUMNS).toContain("code_review");
  });

  it("has exactly 2 gate columns", () => {
    expect(HUMAN_GATE_COLUMNS).toHaveLength(2);
  });
});

describe("WS_EVENTS", () => {
  it("uses dot-delimited event names", () => {
    expect(WS_EVENTS.TICKET_CREATED).toBe("ticket.created");
    expect(WS_EVENTS.AI_STATUS).toBe("ai.status");
    expect(WS_EVENTS.DEPLOY_COMPLETED).toBe("deploy.completed");
  });
});

describe("API_ROUTES", () => {
  it("has required auth routes", () => {
    expect(API_ROUTES.AUTH_LOGIN).toBe("/auth/login");
    expect(API_ROUTES.AUTH_REGISTER).toBe("/auth/register");
    expect(API_ROUTES.AUTH_ME).toBe("/auth/me");
  });

  it("has resource routes", () => {
    expect(API_ROUTES.TICKETS).toBe("/tickets");
    expect(API_ROUTES.PROJECTS).toBe("/projects");
  });
});
