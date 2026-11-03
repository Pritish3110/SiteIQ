import { describe, expect, it } from "vitest";
import { positive, area, ratio } from "./format";
import { niceLength, shoelace } from "./geometry";
import { diffInputs, diffSummaries, normaliseStudy, parseProjectFile, projectFileText, summariseReport } from "./projects";
import type { Report } from "./types";
import { effectiveArea, emptyStudy, missing, nandiSample, toPayload } from "./study";

describe("positive", () => {
  it("treats blanks and junk as missing, never zero", () => {
    for (const text of ["", " ", "abc", "-4", "0", "Infinity"]) expect(positive(text)).toBeNull();
    expect(positive(" 18.5 ")).toBe(18.5);
  });
});

describe("a new study", () => {
  const study = emptyStudy();
  it("assumes no authority, area, road or category", () => {
    expect(study.authorityKey).toBe("");
    expect(effectiveArea(study)).toBeNull();
    expect(missing(study, true)).toEqual(["planning authority", "land-use category", "plot area", "road width"]);
  });
  it("sends unknown overlays as absent from the payload, not as cleared", () => {
    expect(toPayload(study).overlays).toEqual({});
  });
});

describe("toPayload", () => {
  it("uses the boundary area when in use and the typed area when not", () => {
    const sample = nandiSample();
    expect(toPayload(sample).site_area_m2).toBeCloseTo(sample.boundary!.area);
    sample.boundary!.useComputedArea = false;
    sample.siteArea = "1000";
    expect(toPayload(sample).site_area_m2).toBe(1000);
  });
  it("maps edge roles and ignores widths on edges that are not roads", () => {
    const sample = nandiSample();
    sample.boundary!.roadWidths[2] = "9";
    const payload = toPayload(sample);
    expect(payload.boundary!.front_edges).toEqual([0]);
    expect(payload.boundary!.rear_edges).toEqual([2]);
    expect(payload.road_edges).toEqual([{ edge: 0, width_m: 18.5 }]);
  });
  it("sends a declared overlay with its edge and depth", () => {
    const sample = nandiSample();
    sample.overlays.drain = { status: "present", edge: "1", depth: "15", drainClass: "primary" };
    expect(toPayload(sample).overlays.drain).toEqual({ status: "present", edge: 1, extra_setback_m: 15, drain_class: "primary", line_kv: null, max_height_m: null, distance_m: null, flood_level_m: null });
  });
  it("marks an option manual only when a manual setback is entered", () => {
    const sample = nandiSample();
    sample.options[0].manualSetback = "4";
    const [first, second] = toPayload(sample).scenarios;
    expect(first.setback_mode).toBe("manual");
    expect(second.setback_mode).toBe("automatic");
  });
});

describe("helpers", () => {
  it("calculates polygon area", () => expect(shoelace([[0, 0], [10, 0], [10, 5], [0, 5]])).toBe(50));
  it("rounds scale bars", () => { expect(niceLength(23)).toBe(20); expect(niceLength(7)).toBe(5); expect(niceLength(130)).toBe(100); });
  it("formats missing values as a dash", () => { expect(area(null)).toBe("—"); expect(ratio(undefined)).toBe("—"); expect(ratio(2.5)).toBe("2.50"); });
});

describe("floor areas and edge roles in the payload", () => {
  it("sends complete schedule rows only, and exclusions", () => {
    const sample = nandiSample();
    sample.options[0].schedule = [{ name: "Podium", floors: "1", area: "900" }, { name: "Blank", floors: "", area: "" }];
    sample.options[0].corePerFloor = "40";
    sample.options[0].parking = "200";
    const option = toPayload(sample).scenarios[0];
    expect(option.floor_schedule).toEqual([{ name: "Podium", floors: 1, area_m2: 900 }]);
    expect(option.core_excluded_per_floor_m2).toBe(40);
    expect(option.parking_excluded_m2).toBe(200);
  });
  it("sends left and right edges", () => {
    const sample = nandiSample();
    sample.boundary!.roles = { 0: "road", 1: "right", 2: "rear", 4: "left" };
    const boundary = toPayload(sample).boundary!;
    expect(boundary.left_edges).toEqual([4]);
    expect(boundary.right_edges).toEqual([1]);
  });
});

describe("project files", () => {
  it("round-trips a study", () => {
    const sample = nandiSample();
    const project = parseProjectFile(projectFileText(sample, []));
    expect(project.study.projectName).toBe("Nandi Housing");
    expect(project.study.boundary!.area).toBeCloseTo(sample.boundary!.area);
  });
  it("refuses other files", () => {
    expect(() => parseProjectFile("not json")).toThrow(/could not be read/);
    expect(() => parseProjectFile("{\"a\":1}")).toThrow(/not a SiteIQ project/);
  });
  it("fills fields added after a project was saved", () => {
    const study = normaliseStudy({ projectName: "Old", options: [{ name: "A", height: "9" } as never] });
    expect(study.guidanceValue).toBe("");
    expect(study.options[0].schedule).toEqual([]);
    expect(study.options[0].height).toBe("9");
  });
});

describe("revision comparison", () => {
  it("lists changed inputs and skips location data", () => {
    const changes = diffInputs({ road_width_m: 18, location: { a: 1 }, project_name: "A" }, { road_width_m: 6, location: { a: 2 }, project_name: "A" });
    expect(changes).toEqual([{ label: "road width m", from: "18", to: "6" }]);
  });
  it("lists changed results, including rule updates and removed options", () => {
    const base = { verdict: "BLOCKED", maximumFar: 2.5, capacity: 5000, ruleStatus: "x", profileVersion: "1", options: [{ name: "A", floorArea: 100, counted: 90, remaining: 10, envelope: 50 }, { name: "B", floorArea: 1, counted: 1, remaining: 1, envelope: 1 }] };
    const next = { ...base, maximumFar: 2.25, profileVersion: "2", options: [{ ...base.options[0], remaining: -5 }] };
    const labels = diffSummaries(base, next).map((c) => c.label);
    expect(labels).toEqual(["Base FAR", "Rule profile version", "A: remaining (m²)", "B"]);
    expect(diffSummaries(base, base)).toEqual([]);
  });
  it("summarises a report", () => {
    const report = { verdict: { code: "INCOMPLETE" }, maximum_far: 2, maximum_far_area_m2: 10, application: { source_status: "s" }, scenarios: [{ name: "A", gross_concept_area_m2: 5 }] } as unknown as Report;
    expect(summariseReport(report).options[0]).toEqual({ name: "A", floorArea: 5, counted: null, remaining: null, envelope: null });
  });
});
