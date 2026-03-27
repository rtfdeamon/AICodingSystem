import { describe, it, expect } from "vitest";
import {
  isHumanGateColumn,
  canMoveToColumn,
  canCreateTicket,
  canDeployToProduction,
} from "./permissions";

describe("isHumanGateColumn", () => {
  it("returns true for plan_review", () => {
    expect(isHumanGateColumn("plan_review")).toBe(true);
  });

  it("returns true for code_review", () => {
    expect(isHumanGateColumn("code_review")).toBe(true);
  });

  it("returns false for backlog", () => {
    expect(isHumanGateColumn("backlog")).toBe(false);
  });

  it("returns false for production", () => {
    expect(isHumanGateColumn("production")).toBe(false);
  });

  it("returns false for ai_coding", () => {
    expect(isHumanGateColumn("ai_coding")).toBe(false);
  });
});

describe("canMoveToColumn", () => {
  describe("owner role", () => {
    it("can move between any columns", () => {
      expect(canMoveToColumn("owner", "backlog", "production")).toBe(true);
      expect(canMoveToColumn("owner", "plan_review", "ai_coding")).toBe(true);
      expect(canMoveToColumn("owner", "code_review", "staging")).toBe(true);
    });
  });

  describe("pm_lead role", () => {
    it("can move between any columns", () => {
      expect(canMoveToColumn("pm_lead", "backlog", "production")).toBe(true);
      expect(canMoveToColumn("pm_lead", "plan_review", "ai_coding")).toBe(true);
    });
  });

  describe("developer role", () => {
    it("can move within dev-related columns", () => {
      expect(canMoveToColumn("developer", "backlog", "ai_planning")).toBe(true);
      expect(canMoveToColumn("developer", "staging", "staging_verification")).toBe(true);
    });

    it("can approve/reject from review columns (plan_review, code_review)", () => {
      expect(canMoveToColumn("developer", "plan_review", "ai_coding")).toBe(true);
      expect(canMoveToColumn("developer", "plan_review", "backlog")).toBe(true);
      expect(canMoveToColumn("developer", "code_review", "staging")).toBe(true);
      expect(canMoveToColumn("developer", "code_review", "ai_coding")).toBe(true);
    });

    it("cannot deploy to production (only pm_lead can)", () => {
      expect(canMoveToColumn("developer", "staging_verification", "production")).toBe(false);
      expect(canMoveToColumn("developer", "plan_review", "production")).toBe(false);
    });
  });

  describe("ai_agent role", () => {
    it("can move within AI columns", () => {
      expect(canMoveToColumn("ai_agent", "backlog", "ai_planning")).toBe(true);
      expect(canMoveToColumn("ai_agent", "ai_planning", "ai_coding")).toBe(true);
    });

    it("cannot move to production", () => {
      expect(canMoveToColumn("ai_agent", "staging", "production")).toBe(false);
    });

    it("cannot move from non-AI columns", () => {
      expect(canMoveToColumn("ai_agent", "production", "backlog")).toBe(false);
    });

    it("cannot move from human gate columns", () => {
      expect(canMoveToColumn("ai_agent", "plan_review", "ai_coding")).toBe(false);
    });
  });
});

describe("canCreateTicket", () => {
  it("allows owner", () => {
    expect(canCreateTicket("owner")).toBe(true);
  });

  it("allows pm_lead", () => {
    expect(canCreateTicket("pm_lead")).toBe(true);
  });

  it("allows developer", () => {
    expect(canCreateTicket("developer")).toBe(true);
  });

  it("denies ai_agent", () => {
    expect(canCreateTicket("ai_agent")).toBe(false);
  });
});

describe("canDeployToProduction", () => {
  it("allows only pm_lead", () => {
    expect(canDeployToProduction("pm_lead")).toBe(true);
  });

  it("denies owner", () => {
    expect(canDeployToProduction("owner")).toBe(false);
  });

  it("denies developer", () => {
    expect(canDeployToProduction("developer")).toBe(false);
  });

  it("denies ai_agent", () => {
    expect(canDeployToProduction("ai_agent")).toBe(false);
  });
});
