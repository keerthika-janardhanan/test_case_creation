import { test, expect } from "@playwright/test";

const API_BASE = process.env.API_BASE ?? "http://localhost:8000";
const APP_BASE = process.env.APP_BASE ?? "http://localhost:5173";

async function waitForJob(page, jobId: string) {
  await test.step(`poll job ${jobId}`, async () => {
    for (let i = 0; i < 20; i += 1) {
      const response = await page.request.get(`${API_BASE}/api/jobs/${jobId}`);
      expect(response.ok()).toBeTruthy();
      const data = await response.json();
      if (["completed", "failed"].includes(String(data.status).toLowerCase())) {
        return data;
      }
      await page.waitForTimeout(1000);
    }
    throw new Error(`Job ${jobId} did not finish in time`);
  });
}

test.describe("Recorder smoke", () => {
  test("launch recorder job", async ({ page }) => {
    const payload = {
      url: "https://example.com",
      flowName: "smoke-session",
      options: { headless: true },
    };
    const enqueue = await page.request.post(`${API_BASE}/api/recorder/sessions`, {
      data: payload,
    });
    expect(enqueue.ok()).toBeTruthy();
    const body = await enqueue.json();
    const job = await waitForJob(page, body.jobId);
    expect(job.status).toBe("completed");
    expect(job.result.sessionId).toBeDefined();
  });
});

// To run locally:
// 1. Start FastAPI (uvicorn app.api.main:app --reload)
// 2. Start the React dev server (npm run dev)
// 3. Launch: npx playwright test playwright-smoke/smoke.spec.ts --config=playwright.config.ts
//    (add a config if not already present).
