import { useEffect, useRef, useState } from "react";
import {
  Box,
  Button,
  Code,
  FormControl,
  FormHelperText,
  FormLabel,
  Heading,
  Input,
  Stack,
  Text,
  useToast,
} from "@chakra-ui/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ingestDocuments } from "../api/ingest";
import type { JobResponse } from "../api/ingest";
import { getJob } from "../api/jobs";
import type { JobDetail } from "../api/jobs";

export function DocumentsPage() {
  const toast = useToast();
  const [files, setFiles] = useState<FileList | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const lastNotifiedStatus = useRef<string | null>(null);

  const jobQuery = useQuery<{ id: string; detail: JobDetail } | null>({
    queryKey: ["docs-job", activeJobId],
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
        title: "Document ingestion finished",
        description: typeof ing === "number" ? `${ing} docs added ✅` : "Completed",
        status: "success",
      });
      lastNotifiedStatus.current = status;
    } else if (status === "failed") {
      const err = jobQuery.data?.detail?.error || "Document ingestion failed";
      toast({ title: "Document ingestion failed", description: err, status: "error" });
      lastNotifiedStatus.current = status;
    }
  }, [jobQuery.data?.detail?.status, jobQuery.data?.detail?.result, jobQuery.data?.detail?.error, activeJobId, toast]);

  const docsMutation = useMutation<JobResponse, Error, FileList>({
    mutationFn: async (payload) => ingestDocuments(payload),
    onSuccess: (data) => {
      setActiveJobId(data.jobId);
      toast({ title: "Document ingest queued", description: `Job ${data.jobId} created`, status: "success" });
    },
    onError: (error) => {
      toast({ title: "Failed to queue document ingest", description: error.message, status: "error" });
    },
  });

  const handleSubmit = () => {
    if (!files || files.length === 0) {
      toast({ title: "Please select one or more files", status: "warning" });
      return;
    }
    docsMutation.mutate(files);
  };

  return (
    <Stack spacing={6} align="stretch">
      <Heading size="lg">Document Ingestion</Heading>
      <Text color="gray.600">Upload and ingest PDF, DOCX, DOC, or TXT files into the vector database.</Text>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <FormControl mb={4}>
          <FormLabel>Documents</FormLabel>
          <Input
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.txt"
            onChange={(e) => setFiles(e.target.files)}
          />
          <FormHelperText>Select one or more documents to ingest.</FormHelperText>
        </FormControl>
        <Button colorScheme="blue" onClick={handleSubmit} isLoading={docsMutation.isPending}>
          Ingest Uploaded Documents
        </Button>
        {activeJobId && (
          <Stack spacing={1} fontSize="sm" color="gray.600" mt={4}>
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
      </Box>
    </Stack>
  );
}
