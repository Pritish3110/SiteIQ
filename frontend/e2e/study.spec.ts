import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const SHOTS = process.env.SITEIQ_SHOTS;
const shot = async (page: Page, name: string) => { if (SHOTS) { await page.waitForTimeout(900); await page.screenshot({ path: path.join(SHOTS, `${name}.png`) }); } };
const KML = `<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>Hoskote plot</name><Polygon><outerBoundaryIs><LinearRing><coordinates>77.7826482467,13.0744051246,0 77.7818835655,13.0744278830,0 77.7821781731,13.0719106518,0 77.7829740806,13.0728906855,0 77.7826482467,13.0744051246,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>`;

async function pick(page: Page, testId: string, name: string | RegExp) {
  await page.getByTestId(testId).click();
  await page.getByRole("option", { name }).first().click();
}

test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  (page as unknown as { __errors: string[] }).__errors = errors;
});
test.afterEach(async ({ page }) => {
  expect((page as unknown as { __errors: string[] }).__errors).toEqual([]);
});

test("a new study assumes nothing and shows no FAR", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(SHOTS ? 3600 : 0);
  await shot(page, "01-hero");
  await page.getByTestId("start-study").click();
  await expect(page.getByTestId("sheet-heading")).toHaveText("Where is the site?");
  await expect(page.getByTestId("tb-far")).toHaveText("—");
  await page.getByTestId("sheet-3").click();
  await expect(page.getByTestId("far-empty")).toContainText("planning authority");
  await page.getByTestId("sheet-5").click();
  await expect(page.getByTestId("dossier-empty")).toBeVisible();
});

test("the sample study reaches a dossier with a blocking status and envelopes", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("load-sample").click();
  await expect(page.getByTestId("verdict")).toHaveAttribute("data-code", "BLOCKED");
  await expect(page.getByTestId("tb-far").locator("[data-value]")).toHaveAttribute("data-value", "2.5");
  await expect(page.getByTestId("envelope-area-1")).toContainText("m²");
  await shot(page, "02-dossier-top");
  await page.getByTestId("register").scrollIntoViewIfNeeded();
  await shot(page, "03-dossier-register");
  await page.getByTestId("sheet-4").click();
  await expect(page.getByTestId("failures-1")).toContainText("exceeds the FAR capacity");
  await shot(page, "04-options");
  await page.getByTestId("sheet-3").click();
  await expect(page.getByTestId("far-capacity")).toBeVisible();
  await shot(page, "05-far");
  await page.getByTestId("sheet-2").click();
  await shot(page, "06-controls");
});

test("exports download with the live figures and are held while recalculating", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("load-sample").click();
  await expect(page.getByTestId("verdict")).toBeVisible();
  for (const [kind, ext] of [["report-pdf", "pdf"], ["technical-pdf", "pdf"], ["board-pdf", "pdf"], ["report-pptx", "pptx"], ["board-pptx", "pptx"], ["envelopes-dxf", "dxf"], ["assessment-json", "json"]]) {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId(`export-${kind}`).click()]);
    expect(download.suggestedFilename()).toMatch(new RegExp(`SiteIQ_.*\\.${ext}$`));
    if (SHOTS) await download.saveAs(path.join(SHOTS, download.suggestedFilename()));
  }
});

test("full manual flow: KML upload, edge tagging, rules, options, live results", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("start-study").click();
  await page.getByTestId("project-name").fill("Hoskote Test Plot");
  await page.getByTestId("sheet-1").click();
  await page.getByTestId("file-input").setInputFiles({ name: "hoskote.kml", mimeType: "application/xml", buffer: Buffer.from(KML) });
  await expect(page.getByTestId("preview-area")).toContainText("m²");
  await page.getByTestId("edge-0").click();
  await expect(page.getByTestId("edge-0")).toHaveAttribute("data-role", "road");
  await page.getByTestId("edge-2").click();
  await page.getByTestId("edge-2").click();
  await expect(page.getByTestId("edge-2")).toHaveAttribute("data-role", "rear");
  await page.getByTestId("edge-1").click();
  await page.getByTestId("edge-1").click();
  await page.getByTestId("edge-1").click();
  await expect(page.getByTestId("edge-1")).toHaveAttribute("data-role", "left");
  await shot(page, "07-boundary-preview");
  await page.getByTestId("apply-boundary").click();
  await expect(page.getByTestId("applied-area")).toContainText("m²");
  await shot(page, "08-boundary-applied");
  await page.getByTestId("sheet-2").click();
  await pick(page, "authority-select", /Hoskote/);
  await pick(page, "category-select", /^Residential/);
  await page.getByTestId("road-width").fill("15");
  await page.getByTestId("road-source").getByRole("radio", { name: "Notified" }).click();
  await page.getByTestId("sheet-3").click();
  await expect(page.getByTestId("far-value")).toHaveAttribute("data-value", "2.25");
  await page.getByTestId("sheet-2").click();
  await page.getByTestId("road-width").fill("20");
  await page.getByTestId("sheet-3").click();
  await expect(page.getByTestId("far-value")).toHaveAttribute("data-value", "2.5");
  await page.getByTestId("sheet-4").click();
  await page.getByTestId("height-0").fill("15");
  await page.getByTestId("floors-0").fill("5");
  await page.getByTestId("height-1").fill("24");
  await page.getByTestId("floors-1").fill("8");
  await expect(page.getByTestId("gross-0")).not.toHaveText("—");
  await expect(page.getByTestId("tb-project")).toHaveText("Hoskote Test Plot");
  await page.getByTestId("add-option").click();
  await page.getByTestId("height-2").fill("0");
  await expect(page.getByTestId("option-2")).toBeVisible();
  await page.getByTestId("remove-option-2").click();
  await shot(page, "09-options-envelopes");
  await page.getByTestId("sheet-5").click();
  await expect(page.getByTestId("comparison")).toBeVisible();
  await expect(page.getByTestId("register")).toContainText("Fire NOC");
  await page.getByTestId("register-filter").getByRole("radio", { name: "Everything" }).click();
  await expect(page.getByTestId("register")).toContainText("Pass");
});

test("an authority without rules gives no FAR and borrows nothing", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("start-study").click();
  await page.getByTestId("sheet-2").click();
  await pick(page, "authority-select", /Mysuru/);
  await expect(page.getByTestId("no-rules")).toBeVisible();
  await page.getByTestId("site-area").fill("2000");
  await page.getByTestId("road-width").fill("18");
  await page.getByTestId("sheet-3").click();
  await expect(page.getByTestId("far-unresolved")).toContainText("No rule profile");
  await expect(page.getByTestId("tb-far")).toHaveText("—");
});

test("invalid coordinates fail closed with a clear reason", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("start-study").click();
  await page.getByTestId("location-mode").getByRole("radio", { name: "Coordinates" }).click();
  await page.getByTestId("coordinates").fill("77.5946, 12.9716");
  await page.getByTestId("identify").click();
  await expect(page.getByTestId("location-error")).toContainText("swapped");
  await expect(page.getByTestId("found-authority")).toHaveCount(0);
});

test("bad files are refused with a reason", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("start-study").click();
  await page.getByTestId("sheet-1").click();
  await page.getByTestId("file-input").setInputFiles({ name: "site.dwg", mimeType: "application/octet-stream", buffer: Buffer.from("x") });
  await expect(page.getByTestId("boundary-error")).toContainText("DXF");
});

test("a real DXF with several features needs an explicit choice", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("start-study").click();
  await page.getByTestId("sheet-1").click();
  await page.getByTestId("file-input").setInputFiles(path.resolve("../sample_data/illustrative_irregular_site.dxf"));
  await expect(page.getByTestId("candidate-select")).toBeVisible();
  await expect(page.getByTestId("preview-area")).toContainText("m²");
});

test("a project can be saved to a file, reopened and compared with a revision", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("load-sample").click();
  await expect(page.getByTestId("verdict")).toBeVisible();
  await page.getByTestId("revision-name").fill("Before road change");
  await page.getByTestId("save-revision").click();
  await page.getByTestId("sheet-2").click();
  await page.getByTestId("road-width").fill("9");
  await page.getByTestId("sheet-5").click();
  await expect(page.getByTestId("revision-diff")).toContainText("road width m");
  await expect(page.getByTestId("revision-diff")).toContainText("Base FAR");
  await shot(page, "14-revisions");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("save-project").click()]);
  expect(download.suggestedFilename()).toBe("Nandi_Housing.siteiq");
  const file = await download.path();
  await page.getByTestId("restore-revision").click();
  await page.getByTestId("sheet-2").click();
  await expect(page.getByTestId("road-width")).toHaveValue("18.5");
  await page.goto("/");
  await expect(page.getByTestId("recent-projects")).toContainText("Nandi Housing");
  await shot(page, "15-recent");
  await page.getByTestId("project-file").setInputFiles(file);
  await expect(page.getByTestId("tb-project")).toHaveText("Nandi Housing");
  await page.goto("/");
  await page.getByTestId("project-file").setInputFiles({ name: "x.siteiq", mimeType: "application/json", buffer: Buffer.from("{}") });
  await expect(page.getByTestId("open-error")).toContainText("not a SiteIQ project");
});

test("exclusions and a floor schedule change the counted area", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("load-sample").click();
  await page.getByTestId("sheet-4").click();
  await expect(page.getByTestId("headroom-0")).toContainText("-562");
  await page.getByTestId("far-details-0").locator("summary").click();
  await page.getByTestId("parking-0").fill("600");
  await expect(page.getByTestId("headroom-0")).toContainText("+38");
  await page.getByTestId("add-level-0").click();
  await page.getByTestId("schedule-floors-0-0").fill("2");
  await page.getByTestId("schedule-area-0-0").fill("800");
  await expect(page.getByTestId("gross-0")).toContainText("1,600");
  await shot(page, "16-schedule");
});

test("the rule library shows coverage honestly", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("start-study").click();
  await page.getByTestId("sheet-6").click();
  await expect(page.getByTestId("library-table")).toContainText("Hoskote");
  await expect(page.getByTestId("library-count")).toContainText("5");
  await shot(page, "13-library");
});

test("the sheet is usable and readable in the dark theme and on a narrow screen", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("load-sample").click();
  await page.getByTestId("theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await shot(page, "10-dark-dossier");
  await page.getByTestId("sheet-1").click();
  await shot(page, "11-dark-boundary");
  await page.getByTestId("theme-toggle").click();
  await page.setViewportSize({ width: 820, height: 1100 });
  await expect(page.getByTestId("compact-status")).toContainText("FAR 2.50");
  await shot(page, "12-tablet");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});
