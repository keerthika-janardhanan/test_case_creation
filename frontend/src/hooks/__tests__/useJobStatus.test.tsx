import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

import { useJobStatus } from "../useJobStatus";
import type { JobDetail } from "../../api/jobs";

vi.mock("../../api/jobs", async (importOriginal) => {
  const actual = await importOriginal<any>();
  return {
    ...actual,
    getJob: vi.fn(() =>
      Promise.resolve({
        jobId: "job-1",
        type: "recorder.launch",
        status: "completed",
        payload: {},
        result: { hello: "world" },
        error: null,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      } satisfies JobDetail),
    ),
  };
});

function renderUseJobStatus(jobId: string | null) {
  const queryClient = new QueryClient();
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useJobStatus(jobId, 10), { wrapper });
}

describe("useJobStatus", () => {
  it("fetches job data when id provided", async () => {
    const { result } = renderUseJobStatus("job-1");
    await waitFor(() => {
      expect(result.current.data?.status).toBe("completed");
    });
  });

  it("does not run when id is null", () => {
    const { result } = renderUseJobStatus(null);
    expect(result.current.isFetching).toBe(false);
  });
});
