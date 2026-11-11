import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { samplePdf } from "./samplePdf";

const LINES = [
  "Certificate of Analysis",
  "Product: Example Tablets 10 mg",
  "Batch: EX-1001",
  "Manufacturing date: 12 March 2026",
  "Expiry date: 31 March 2028",
  "Approved by QA on 20 March 2026",
];

test("upload, wait for done, accept a date, export CSV", async ({ page }) => {
  // A name unique to this run, so a reused dev database still shows one fresh row.
  const name = `smoke-${Date.now()}.pdf`;
  await page.goto("/");
  await page.getByLabel("Choose files to upload").setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: samplePdf(LINES),
  });

  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name }) });
  await expect(row.getByText("Done", { exact: true })).toBeVisible({ timeout: 60_000 });
  await row.getByRole("link", { name }).click();

  const dates = page.getByRole("complementary", { name: "Dates" });
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
  const csv = await readFile((await (await download).path())!, "utf-8");
  expect(csv.split("\n")[0]).toContain("status");
  expect(csv).toContain(",accepted,");
  expect(csv).toContain("Smoke Tester");
});
