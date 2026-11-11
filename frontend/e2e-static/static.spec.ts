import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { samplePdf } from "../e2e/samplePdf";
import { PAGES_PORT } from "./ports";

const LINES = [
  "Certificate of Analysis",
  "Product: Example Tablets 10 mg",
  "Batch: EX-1001",
  "Manufacturing date: 12 March 2026",
  "Expiry date: 31 March 2028",
  "Approved by QA on 20 March 2026",
];

const BANNER = "Runs in your browser · rules only (no AI) · documents are not uploaded anywhere · every date needs review";

/** The only places the static build may load from besides its own origin: pinned engine assets. */
const PINNED = [
  "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/",
  "https://cdn.jsdelivr.net/npm/tesseract.js-core@7.0.0/",
  "https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/",
];

function watchNetwork(page: Page, origin: string) {
  const offsite: string[] = [];
  const sent: string[] = [];
  const pinned: string[] = [];
  const errors: string[] = [];
  // Workers' requests (pdf.js, Tesseract, Pyodide) reach the context, not the page.
  page.context().on("request", (request) => {
    const url = request.url();
    if (url.startsWith("blob:") || url.startsWith("data:")) return;
    if (request.method() !== "GET") sent.push(`${request.method()} ${url}`);
    if (PINNED.some((p) => url.startsWith(p))) pinned.push(url);
    else if (!url.startsWith(origin)) offsite.push(url);
  });
  page.on("console", (message) => {
    // Tesseract prints its own diagnostics ("Estimating resolution as 530") to stderr.
    if (message.type() === "error" && !message.text().startsWith("Estimating resolution")) errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return { offsite, sent, pinned, errors };
}

/** A scanned page: black text on white paper, rendered by the browser and captured as a PNG. */
async function scannedPng(page: Page): Promise<Buffer> {
  const scan = await page.context().newPage();
  await scan.setViewportSize({ width: 1400, height: 300 });
  await scan.setContent(
    `<body style="margin:0;background:#fff"><p style="font:56px Arial,sans-serif;color:#000;margin:110px 60px">Expiry date: 31/03/2027</p></body>`,
  );
  const png = await scan.screenshot({ type: "png" });
  await scan.close();
  return png;
}

async function upload(page: Page, name: string, mimeType: string, buffer: Buffer) {
  await page.getByLabel("Choose files to upload").setInputFiles({ name, mimeType, buffer });
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name }) });
  await expect(row.getByText("Done", { exact: true })).toBeVisible({ timeout: 180_000 });
  return row;
}

test("reads a native PDF in the browser, reviews a date and exports CSV", async ({ page, baseURL }) => {
  const network = watchNetwork(page, new URL(baseURL!).origin);
  await page.goto("./");
  await expect(page.getByRole("note")).toHaveText(BANNER);
  await expect(page.getByText("Rules only", { exact: true })).toBeVisible();

  const name = "coa-native.pdf";
  const row = await upload(page, name, "application/pdf", samplePdf(LINES));
  await expect(row.getByRole("cell").filter({ hasText: /^3$/ }).first()).toBeVisible();
  await row.getByRole("link", { name }).click();
  await expect(page).toHaveURL(/\/pharma-ocr-date-rag\/documents\/\d+$/);

  const dates = page.getByRole("complementary", { name: "Dates" });
  await expect(dates.locator(".date-row")).toHaveCount(3);
  await expect(dates.getByText("2028-03-31")).toBeVisible();
  // The page image rendered in the browser, with a highlight box per date.
  await expect(page.locator(".viewer__image")).toBeVisible();
  expect(await page.locator(".viewer__image").evaluate((img) => (img as { naturalWidth: number }).naturalWidth)).toBe(1700);
  await expect(page.locator(".viewer__box")).toHaveCount(3);

  const first = dates.locator(".date-row").first();
  await first.locator(".date-row__select").click();
  await first.getByRole("button", { name: /^Accept/ }).click();
  const dialog = page.getByRole("dialog", { name: "Accept date" });
  await dialog.getByLabel("Reviewer").fill("Smoke Tester");
  await dialog.getByLabel("Reason").fill("Matches the page");
  await dialog.getByRole("button", { name: "Accept date" }).click();
  await expect(dialog).toBeHidden();
  await expect(first.getByText("Accepted", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Export" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /Export CSV/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^coa-native-run-\d+\.csv$/);
  const csv = await readFile((await file.path())!, "utf-8");
  expect(csv.split("\n")[0]).toContain("status");
  expect(csv).toContain(",accepted,");
  expect(csv).toContain("Smoke Tester");

  // A reload keeps the document and the decision (IndexedDB), on the deep link GitHub Pages serves.
  await page.reload();
  await expect(dates.locator(".date-row").first().getByText("Accepted", { exact: true })).toBeVisible();

  expect(network.sent).toEqual([]);
  expect(network.offsite).toEqual([]);
  expect(network.errors).toEqual([]);
  // The Python core really ran in Pyodide (pinned on jsDelivr).
  expect(network.pinned.some((url) => url.startsWith(PINNED[0]) && url.includes("pydantic"))).toBe(true);
});

test("reads a scanned PNG with OCR in the browser", async ({ page, baseURL }) => {
  const network = watchNetwork(page, new URL(baseURL!).origin);
  await page.goto("./");
  const row = await upload(page, "scan.png", "image/png", await scannedPng(page));
  await row.getByRole("link", { name: "scan.png" }).click();
  const dates = page.getByRole("complementary", { name: "Dates" });
  await expect(dates.locator(".date-row").first()).toBeVisible();
  expect(await dates.locator(".date-row").count()).toBeGreaterThanOrEqual(1);
  await expect(dates.getByText("2027-03-31")).toBeVisible();
  await expect(page.locator(".viewer__box").first()).toBeVisible();
  expect(network.sent).toEqual([]);
  expect(network.offsite).toEqual([]);
  expect(network.errors).toEqual([]);
  expect(network.pinned.some((url) => url.startsWith(PINNED[2]))).toBe(true); // Tesseract's eng data
});

test("refuses an unsupported file", async ({ page }) => {
  await page.goto("./");
  await page.getByLabel("Choose files to upload").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await expect(page.getByRole("alert")).toContainText("notes.txt is not a supported file");
});

test("works as GitHub Pages serves it: base path, deep links via 404.html", async ({ page }) => {
  const root = `http://127.0.0.1:${PAGES_PORT}/pharma-ocr-date-rag/`;
  const network = watchNetwork(page, new URL(root).origin);
  await page.goto(root);
  await expect(page.getByRole("heading", { level: 1, name: "Documents" })).toBeVisible();
  await upload(page, "coa-pages.pdf", "application/pdf", samplePdf(LINES));
  await page.getByRole("link", { name: "coa-pages.pdf" }).click();
  const url = page.url();
  expect(url).toMatch(/\/pharma-ocr-date-rag\/documents\/\d+$/);

  const response = await page.goto(url); // a deep link: GitHub Pages answers with 404.html
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("complementary", { name: "Dates" }).locator(".date-row")).toHaveCount(3);
  await expect(page.locator(".viewer__image")).toBeVisible();
  await page.getByRole("link", { name: "Documents" }).first().click();
  await expect(page).toHaveURL(root.replace(/\/$/, ""));
  expect(network.offsite).toEqual([]);
  expect(network.errors.filter((e) => !e.includes("404"))).toEqual([]);
});
