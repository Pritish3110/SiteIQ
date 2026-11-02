import { defineConfig } from "@playwright/test";

// SITEIQ_PYTHON points at the Python environment holding requirements.txt.
const python = process.env.SITEIQ_PYTHON ?? "../.venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8765", channel: "chrome", viewport: { width: 1600, height: 1000 } },
  webServer: { command: `"${python}" -m uvicorn siteiq.api:app --host 127.0.0.1 --port 8765`, cwd: "..", url: "http://127.0.0.1:8765/api/meta", reuseExistingServer: true },
});
