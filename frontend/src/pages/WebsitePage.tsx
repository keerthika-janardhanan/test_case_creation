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
  Input,
  NumberInput,
  NumberInputField,
  Stack,
  Text,
  useToast,
} from "@chakra-ui/react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ingestWebsite } from "../api/ingest";
import type { JobResponse } from "../api/ingest";
import { getJob } from "../api/jobs";
import type { JobDetail } from "../api/jobs";

export function WebsitePage() {
  const toast = useToast();
  const [url, setUrl] = useState("https://docs.oracle.com/en/cloud/saas/index.html");
  const [maxDepth, setMaxDepth] = useState<number>(2);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const lastNotifiedStatus = useRef<string | null>(null);

  const jobQuery = useQuery<{ id: string; detail: JobDetail } | null>({
    queryKey: ["website-job", activeJobId],
    enabled: !!activeJobId,
    queryFn: async () => {
      if (!activeJobId) return null;
      const detail = await getJob(activeJobId);
      return { id: activeJobId, detail };
    },
    refetchInterval: (q) => {
      const status = q.state.data?.detail?.status;
      return status && ["pending", "queued", "running"].includes(status) ? 2000 : false;
    },
  });

  useEffect(() => {
    const status = jobQuery.data?.detail?.status;
    if (!status || !activeJobId) return;
    if (status === lastNotifiedStatus.current) return;
    if (status === "completed") {
      const ing = (jobQuery.data?.detail?.result as any)?.ingested;
      toast({
        title: "Website ingestion finished",
        description: typeof ing === "number" ? `${ing} docs added ✅` : "Completed",
        status: "success",
      });
      lastNotifiedStatus.current = status;
    } else if (status === "failed") {
      const err = jobQuery.data?.detail?.error || "Website ingestion failed";
      toast({ title: "Website ingestion failed", description: err, status: "error" });
      lastNotifiedStatus.current = status;
    }
  }, [jobQuery.data?.detail?.status, jobQuery.data?.detail?.result, jobQuery.data?.detail?.error, activeJobId, toast]);

  const websiteMutation = useMutation<JobResponse, Error, { url: string; maxDepth: number }>({
    mutationFn: async (payload) => ingestWebsite(payload),
    onSuccess: (data) => {
      setActiveJobId(data.jobId);
      toast({ title: "Website ingest queued", description: `Job ${data.jobId} created`, status: "success" });
    },
    onError: (error) => {
      toast({ title: "Failed to queue website ingest", description: error.message, status: "error" });
    },
  });

  const handleSubmit = () => {
    const trimmed = (url || "").trim();
    if (!trimmed) {
      toast({ title: "Please enter a valid URL", status: "warning" });
      return;
    }
    try {
      // Basic sanity: ensure http/https
      let normalized = trimmed;
      if (!/^https?:\/\//i.test(normalized)) {
        normalized = `https://${normalized}`;
      }
      // new URL will throw on invalid
      // eslint-disable-next-line no-new
      new URL(normalized);
      websiteMutation.mutate({ url: normalized, maxDepth });
    } catch {
      toast({ title: "Please enter a valid URL", status: "warning" });
    }
  };

  return (
    <Stack spacing={6} align="stretch">
      <Heading size="lg">Website Ingestion</Heading>
      <Text color="gray.600">Crawl a website and ingest content into the vector database.</Text>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Stack spacing={4}>
          <FormControl>
            <FormLabel>Website URL</FormLabel>
            <Input
              value={url}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setUrl(event.target.value)}
              placeholder="https://docs.oracle.com/en/cloud/saas/index.html"
            />
            <FormHelperText>Start URL to crawl.</FormHelperText>
          </FormControl>

          <FormControl maxW="220px">
            <FormLabel>Max Depth</FormLabel>
            <NumberInput min={1} max={5} value={maxDepth} onChange={(_, valueAsNumber) => setMaxDepth(valueAsNumber || 1)}>
              <NumberInputField />
            </NumberInput>
            <FormHelperText>Limit crawl depth (1-5).</FormHelperText>
          </FormControl>

          <Button colorScheme="blue" onClick={handleSubmit} isLoading={websiteMutation.isPending}>
            Fetch & Ingest Website
          </Button>

          {activeJobId && (
            <Stack spacing={1} fontSize="sm" color="gray.600">
              <Text>
                Active job: <Code>{activeJobId}</Code>
              </Text>
              <Text>
                Status: <Code>{jobQuery.data?.detail?.status ?? (jobQuery.isFetching ? "pending" : "queued")}</Code>
              </Text>
              {typeof (jobQuery.data?.detail?.result as any)?.ingested === "number" && (
                <Text>Ingested: {(jobQuery.data?.detail?.result as any).ingested}</Text>
              )}
            </Stack>
          )}
        </Stack>
      </Box>
    </Stack>
  );
}
