import { useQuery } from "@tanstack/react-query";

import type { JobDetail } from "../api/jobs";
import { getJob } from "../api/jobs";

export function useJobStatus(jobId: string | null, pollInterval = 2000) {
  return useQuery<JobDetail, Error>({
    queryKey: ["job-status", jobId],
    queryFn: () => getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (data) => {
      if (!data || !data.status) {
        return pollInterval;
      }
      const status = String(data.status).toLowerCase();
      const terminal = new Set(["completed", "failed"]);
      return terminal.has(status) ? false : pollInterval;
    },
  });
}
