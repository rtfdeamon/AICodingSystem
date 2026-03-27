import { describe, it, expect } from "vitest";
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatPriority,
  getPriorityClasses,
  formatColumnName,
  truncateText,
} from "./formatters";

describe("formatDate", () => {
  it("formats a date string", () => {
    const result = formatDate("2026-01-15T10:30:00Z");
    expect(result).toBe("Jan 15, 2026");
  });

  it("formats a Date object", () => {
    const result = formatDate(new Date(2026, 5, 20));
    expect(result).toBe("Jun 20, 2026");
  });
});

describe("formatDateTime", () => {
  it("includes time component", () => {
    const result = formatDateTime("2026-03-15T14:30:00Z");
    expect(result).toContain("2026");
    expect(result).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i);
  });
});

describe("formatDuration", () => {
  it("formats days, hours, minutes", () => {
    const ms = (2 * 86400 + 3 * 3600 + 45 * 60) * 1000;
    expect(formatDuration(ms)).toBe("2d 3h 45m");
  });

  it("formats hours and minutes", () => {
    const ms = (1 * 3600 + 30 * 60) * 1000;
    expect(formatDuration(ms)).toBe("1h 30m");
  });

  it("formats minutes only", () => {
    const ms = 5 * 60 * 1000;
    expect(formatDuration(ms)).toBe("5m");
  });

  it("returns < 1m for sub-minute duration", () => {
    expect(formatDuration(30000)).toBe("< 1m");
  });

  it("returns < 1m for zero", () => {
    expect(formatDuration(0)).toBe("< 1m");
  });
});

describe("formatPriority", () => {
  it("maps P0 to label", () => {
    expect(formatPriority("P0")).toBe("P0 - Critical");
  });

  it("maps P3 to label", () => {
    expect(formatPriority("P3")).toBe("P3 - Low");
  });
});

describe("getPriorityClasses", () => {
  it("returns CSS classes for P0", () => {
    const classes = getPriorityClasses("P0");
    expect(classes).toContain("bg-red");
    expect(classes).toContain("text-red");
  });

  it("returns CSS classes for P2", () => {
    const classes = getPriorityClasses("P2");
    expect(classes).toContain("bg-yellow");
  });
});

describe("formatColumnName", () => {
  it("formats backlog", () => {
    expect(formatColumnName("backlog")).toBe("Backlog");
  });

  it("formats ai_planning", () => {
    expect(formatColumnName("ai_planning")).toBe("AI Planning");
  });

  it("formats production", () => {
    expect(formatColumnName("production")).toBe("Production");
  });
});

describe("truncateText", () => {
  it("returns text unchanged if shorter than max", () => {
    expect(truncateText("hello", 100)).toBe("hello");
  });

  it("truncates long text with ellipsis", () => {
    const long = "a".repeat(150);
    const result = truncateText(long, 100);
    expect(result.length).toBeLessThanOrEqual(103); // 100 + "..."
    expect(result).toMatch(/\.\.\.$/);
  });

  it("uses default maxLength of 100", () => {
    const long = "x".repeat(200);
    const result = truncateText(long);
    expect(result).toMatch(/\.\.\.$/);
  });

  it("returns exact length text unchanged", () => {
    const text = "a".repeat(100);
    expect(truncateText(text, 100)).toBe(text);
  });
});
