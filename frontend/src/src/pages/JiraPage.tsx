import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";

import {
  Box,
  Button,
  Code,
  FormControl,
  FormHelperText,
  FormLabel,
  Heading,
  HStack,
  Stack,
  Text,
  Textarea,
  useToast,
} from "@chakra-ui/react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ingestJira } from "../api/ingest";
import type { JobResponse } from "../api/ingest";
import { getJob } from "../api/jobs";
import type { JobDetail } from "../api/jobs";

type JiraHistoryItem = {
  jobId: string;
  jql: string;
  ts: string; // ISO timestamp
};

const HISTORY_KEY = "jiraIngestHistory";
const MAX_HISTORY = 8;

function loadHistory(): JiraHistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as JiraHistoryItem[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHistory(items: JiraHistoryItem[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)));
  } catch {
    // ignore storage errors
  }
}

export function JiraPage() {
  const toast = useToast();
  const [jql, setJql] = useState("project=GEN_AI_PROJECT ORDER BY created DESC");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [history, setHistory] = useState<JiraHistoryItem[]>(() => loadHistory());
  const lastNotifiedStatus = useRef<string | null>(null);

  // Track the most recent job's details
  const jobQuery = useQuery<{ id: string; detail: JobDetail } | null>({
    queryKey: ["jira-job", activeJobId],
    enabled: !!activeJobId,
    queryFn: async () => {
      if (!activeJobId) return null;
      const detail = await getJob(activeJobId);
      return { id: activeJobId, detail };
    },
    refetchInterval: (q) => {
      // Poll while job is pending/queued/running
      const status = q.state.data?.detail?.status;
      return status && ["pending", "queued", "running"].includes(status) ? 2000 : false;
    },
  });

  // Mimic Streamlit UX: when job completes, toast the ingested count; on failure, show error
  useEffect(() => {
    const status = jobQuery.data?.detail?.status;
    if (!status || !activeJobId) return;
    if (status === lastNotifiedStatus.current) return;
    if (status === "completed") {
      const ing = (jobQuery.data?.detail?.result as any)?.ingested;
      toast({
        title: "Jira stories ingested",
        description: typeof ing === "number" ? `${ing} issues ✅` : "Completed",
        status: "success",
      });
      lastNotifiedStatus.current = status;
    } else if (status === "failed") {
      const err = jobQuery.data?.detail?.error || "Jira ingestion failed";
      toast({ title: "Jira ingestion failed", description: err, status: "error" });
      lastNotifiedStatus.current = status;
    }
  }, [jobQuery.data?.detail?.status, jobQuery.data?.detail?.result, jobQuery.data?.detail?.error, activeJobId, toast]);

  const jiraMutation = useMutation<JobResponse, Error, string>({
    mutationFn: async (query) => ingestJira({ jql: query }),
    onSuccess: (data, variables) => {
      setActiveJobId(data.jobId);
      const next: JiraHistoryItem[] = [
        { jobId: data.jobId, jql: variables, ts: new Date().toISOString() },
        ...history.filter((h) => h.jobId !== data.jobId),
      ].slice(0, MAX_HISTORY);
      setHistory(next);
      saveHistory(next);
      toast({ title: "Jira ingest queued", description: `Job ${data.jobId} created`, status: "success" });
    },
    onError: (error) => {
      toast({ title: "Failed to queue Jira ingest", description: error.message, status: "error" });
    },
  });

  const handleSubmit = () => {
    if (!jql.trim()) {
      toast({ title: "JQL required", status: "warning" });
      return;
    }
    jiraMutation.mutate(jql.trim());
  };

  const handleHistoryClick = async (item: JiraHistoryItem) => {
    setActiveJobId(item.jobId);
  };

  const handleClearHistory = () => {
    setHistory([]);
    saveHistory([]);
  };

  const latestStatus = jobQuery.data?.detail?.status;
  const latestIngested = (jobQuery.data?.detail?.result as any)?.ingested;

  return (
    <Stack spacing={6} align="stretch">
      <Heading size="lg">Jira Ingestion</Heading>
      <Text color="gray.600">Queue Jira issues to ingest into the vector database.</Text>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <FormControl mb={4}>
          <FormLabel>JQL query</FormLabel>
          <Textarea
            value={jql}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setJql(event.target.value)}
            placeholder="project=GEN_AI_PROJECT ORDER BY created DESC"
          />
          <FormHelperText>Provide the JQL to fetch issues for ingestion.</FormHelperText>
        </FormControl>
        <Button colorScheme="blue" onClick={handleSubmit} isLoading={jiraMutation.isPending}>
          Fetch & Ingest Jira
        </Button>

        {activeJobId && (
          <Stack spacing={1} fontSize="sm" color="gray.600" mt={4}>
            <Text>
              Active job: <Code>{activeJobId}</Code>
            </Text>
            <Text>
              Status: <Code>{latestStatus ?? (jobQuery.isFetching ? "pending" : "queued")}</Code>
            </Text>
            {typeof latestIngested === "number" && <Text>Ingested: {latestIngested}</Text>}
          </Stack>
        )}
      </Box>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <HStack justify="space-between" mb={3}>
          <Heading size="md">Recent Jira Ingest Jobs</Heading>
          <Button size="sm" variant="outline" onClick={handleClearHistory}>Clear</Button>
        </HStack>
        {history.length === 0 ? (
          <Text color="gray.500">No recent jobs.</Text>
        ) : (
          <Stack spacing={3}>
            {history.map((h) => (
              <Box
                key={h.jobId}
                borderWidth="1px"
                borderRadius="md"
                p={3}
                _hover={{ bg: "gray.50", cursor: "pointer" }}
                onClick={() => handleHistoryClick(h)}
              >
                <Text fontSize="sm" color="gray.600">{new Date(h.ts).toLocaleString()}</Text>
                <Text fontWeight="medium">Job: <Code>{h.jobId}</Code></Text>
                <Text noOfLines={2} color="gray.700" mt={1}>{h.jql}</Text>
              </Box>
            ))}
          </Stack>
        )}
      </Box>
    </Stack>
  );
}
