import { useState } from "react";
import type { ChangeEvent } from "react";

import {
  Box,
  Button,
  Code,
  Flex,
  FormControl,
  FormHelperText,
  FormLabel,
  Heading,
  HStack,
  Input,
  NumberInput,
  NumberInputField,
  Stack,
  Text,
  Textarea,
  useToast,
} from "@chakra-ui/react";
import { useMutation } from "@tanstack/react-query";

import {
  deleteVectorDoc,
  deleteVectorSource,
  ingestDocuments,
  ingestJira,
  ingestWebsite,
} from "../api/ingest";
import type { JobResponse } from "../api/ingest";
import { getJob } from "../api/jobs";
import type { JobDetail } from "../api/jobs";
import { useJobStatus } from "../hooks/useJobStatus";

export function AdminPage() {
  const toast = useToast();

  const [jiraQuery, setJiraQuery] = useState(
    "project=GEN_AI_PROJECT ORDER BY created DESC",
  );
  const [websiteUrl, setWebsiteUrl] = useState("https://example.com");
  const [websiteDepth, setWebsiteDepth] = useState(2);
  const [documentFiles, setDocumentFiles] = useState<FileList | null>(null);
  const [vectorDocId, setVectorDocId] = useState("");
  const [vectorSource, setVectorSource] = useState("");
  const [jobLookupId, setJobLookupId] = useState("");
  const [jobLookupResult, setJobLookupResult] = useState<JobDetail | null>(null);
  const [jiraJobId, setJiraJobId] = useState<string | null>(null);
  const [websiteJobId, setWebsiteJobId] = useState<string | null>(null);
  const [documentsJobId, setDocumentsJobId] = useState<string | null>(null);
  const [vectorDocJobId, setVectorDocJobId] = useState<string | null>(null);
  const [vectorSourceJobId, setVectorSourceJobId] = useState<string | null>(null);

  const jiraMutation = useMutation<JobResponse, Error, string>(
    {
      mutationFn: async (jql) => ingestJira({ jql }),
      onSuccess: (data) => {
        setJiraJobId(data.jobId);
        toast({
          title: "Jira ingest queued",
          description: `Job ${data.jobId} created.`,
          status: "success",
        });
      },
      onError: (error) => {
        setJiraJobId(null);
        toast({
          title: "Failed to queue Jira ingest",
          description: error.message,
          status: "error",
        });
      },
    },
  );

  const websiteMutation = useMutation<JobResponse, Error, { url: string; maxDepth: number }>(
    {
      mutationFn: ingestWebsite,
      onSuccess: (data) => {
        setWebsiteJobId(data.jobId);
        toast({
          title: "Website crawl queued",
          description: `Job ${data.jobId} created.`,
          status: "success",
        });
      },
      onError: (error) => {
        setWebsiteJobId(null);
        toast({
          title: "Failed to queue crawl",
          description: error.message,
          status: "error",
        });
      },
    },
  );

  const documentsMutation = useMutation<JobResponse, Error, FileList>({
    mutationFn: ingestDocuments,
    onSuccess: (data) => {
      setDocumentsJobId(data.jobId);
      toast({
        title: "Document ingest queued",
        description: `Job ${data.jobId} created.`,
        status: "success",
      });
      setDocumentFiles(null);
    },
    onError: (error) => {
      setDocumentsJobId(null);
      toast({
        title: "Failed to queue documents",
        description: error.message,
        status: "error",
      });
    },
  });

  const vectorDocMutation = useMutation<JobResponse, Error, string>({
    mutationFn: deleteVectorDoc,
    onSuccess: (data) => {
      setVectorDocJobId(data.jobId);
      toast({
        title: "Vector document delete queued",
        description: `Job ${data.jobId} created.`,
        status: "success",
      });
    },
    onError: (error) => {
      setVectorDocJobId(null);
      toast({
        title: "Failed to queue delete",
        description: error.message,
        status: "error",
      });
    },
  });

  const vectorSourceMutation = useMutation<JobResponse, Error, string>({
    mutationFn: deleteVectorSource,
    onSuccess: (data) => {
      setVectorSourceJobId(data.jobId);
      toast({
        title: "Vector source delete queued",
        description: `Job ${data.jobId} created.`,
        status: "success",
      });
    },
    onError: (error) => {
      setVectorSourceJobId(null);
      toast({
        title: "Failed to queue source delete",
        description: error.message,
        status: "error",
      });
    },
  });

  const jobLookupMutation = useMutation<JobDetail, Error, string>({
    mutationFn: getJob,
    onSuccess: (data) => {
      setJobLookupResult(data);
    },
    onError: (error) => {
      toast({
        title: "Job lookup failed",
        description: error.message,
        status: "error",
      });
      setJobLookupResult(null);
    },
  });

  const jiraJobStatus = useJobStatus(jiraJobId);
  const websiteJobStatus = useJobStatus(websiteJobId);
  const documentsJobStatus = useJobStatus(documentsJobId);
  const vectorDocJobStatus = useJobStatus(vectorDocJobId);
  const vectorSourceJobStatus = useJobStatus(vectorSourceJobId);

  const handleJiraSubmit = () => {
    if (!jiraQuery.trim()) {
      toast({ title: "JQL required", status: "warning" });
      return;
    }
    jiraMutation.mutate(jiraQuery.trim());
  };

  const handleWebsiteSubmit = () => {
    if (!websiteUrl.trim()) {
      toast({ title: "Website URL required", status: "warning" });
      return;
    }
    websiteMutation.mutate({ url: websiteUrl.trim(), maxDepth: websiteDepth });
  };

  const handleDocumentsSubmit = () => {
    if (!documentFiles || documentFiles.length === 0) {
      toast({ title: "Select at least one file", status: "warning" });
      return;
    }
    documentsMutation.mutate(documentFiles);
  };

  const handleVectorDocDelete = () => {
    if (!vectorDocId.trim()) {
      toast({ title: "Document ID required", status: "warning" });
      return;
    }
    vectorDocMutation.mutate(vectorDocId.trim());
  };

  const handleVectorSourceDelete = () => {
    if (!vectorSource.trim()) {
      toast({ title: "Source required", status: "warning" });
      return;
    }
    vectorSourceMutation.mutate(vectorSource.trim());
  };

  const handleJobLookup = () => {
    if (!jobLookupId.trim()) {
      toast({ title: "Job ID required", status: "warning" });
      return;
    }
    jobLookupMutation.mutate(jobLookupId.trim());
  };

  return (
    <Flex gap={6} align="flex-start">
      {/* Main content: Only Jira Ingestion */}
      <Box flex="1" as={Stack} spacing={6} align="stretch">
        <Heading size="lg">Jira Ingestion</Heading>
        <Text color="gray.600">
          Queue Jira issue ingestion into the vector store.
        </Text>

        <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
          <FormControl mb={4}>
            <FormLabel>JQL query</FormLabel>
            <Textarea
              value={jiraQuery}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setJiraQuery(event.target.value)}
            />
            <FormHelperText>Provide the query to fetch issues for ingestion.</FormHelperText>
          </FormControl>
          <Button
            colorScheme="blue"
            onClick={handleJiraSubmit}
            isLoading={jiraMutation.isPending}
          >
            Queue Jira Ingest
          </Button>
          {jiraJobId && (
            <Stack spacing={1} fontSize="sm" color="gray.600" mt={3}>
              <Text>
                Job: <Code>{jiraJobId}</Code>
              </Text>
              <Text>
                Status:{" "}
                <Code>
                  {jiraJobStatus.data?.status ?? (jiraJobStatus.isFetching ? "pending" : "queued")}
                </Code>
              </Text>
              {typeof jiraJobStatus.data?.result?.ingested === "number" && (
                <Text>Ingested: {jiraJobStatus.data.result.ingested}</Text>
              )}
            </Stack>
          )}
        </Box>
      </Box>

      {/* Page sidebar: quick actions (including Jira), crawl, docs, vector, job lookup */}
      <Box w={{ base: "100%", lg: "360px" }} position="sticky" top={0} alignSelf="start">
        <Stack spacing={6}>
          <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
            <Heading size="sm" mb={3}>Quick Jira Ingest</Heading>
            <FormControl mb={3}>
              <Textarea
                size="sm"
                value={jiraQuery}
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setJiraQuery(event.target.value)}
                placeholder="project=GEN_AI_PROJECT ORDER BY created DESC"
              />
            </FormControl>
            <Button size="sm" colorScheme="blue" onClick={handleJiraSubmit} isLoading={jiraMutation.isPending}>
              Queue
            </Button>
          </Box>

          <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
            <Heading size="sm" mb={3}>Website Crawl</Heading>
            <FormControl mb={3}>
              <FormLabel fontSize="sm">Website URL</FormLabel>
              <Input
                size="sm"
                value={websiteUrl}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setWebsiteUrl(event.target.value)}
                placeholder="https://example.com"
              />
            </FormControl>
            <FormControl mb={3}>
              <FormLabel fontSize="sm">Max depth</FormLabel>
              <NumberInput size="sm" value={websiteDepth} min={1} max={5} onChange={(_, value) => setWebsiteDepth(value || 1)}>
                <NumberInputField />
              </NumberInput>
            </FormControl>
            <Button size="sm" colorScheme="blue" onClick={handleWebsiteSubmit} isLoading={websiteMutation.isPending}>
              Queue Crawl
            </Button>
          </Box>

          <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
            <Heading size="sm" mb={3}>Document Uploads</Heading>
            <FormControl mb={3}>
              <FormLabel fontSize="sm">Select files</FormLabel>
              <Input type="file" multiple onChange={(event: ChangeEvent<HTMLInputElement>) => setDocumentFiles(event.target.files)} />
              <FormHelperText>PDF, DOCX, TXT</FormHelperText>
            </FormControl>
            <Button size="sm" colorScheme="blue" onClick={handleDocumentsSubmit} isLoading={documentsMutation.isPending}>
              Queue Upload
            </Button>
          </Box>

          <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
            <Heading size="sm" mb={3}>Vector Store</Heading>
            <FormControl mb={2}>
              <FormLabel fontSize="sm">Document ID</FormLabel>
              <Input size="sm" value={vectorDocId} onChange={(event: ChangeEvent<HTMLInputElement>) => setVectorDocId(event.target.value)} placeholder="Enter document ID" />
            </FormControl>
            <Button size="sm" variant="outline" onClick={handleVectorDocDelete} isLoading={vectorDocMutation.isPending} mb={3}>
              Delete by ID
            </Button>
            <FormControl mb={2}>
              <FormLabel fontSize="sm">Source</FormLabel>
              <Input size="sm" value={vectorSource} onChange={(event: ChangeEvent<HTMLInputElement>) => setVectorSource(event.target.value)} placeholder="jira, website, etc." />
            </FormControl>
            <Button size="sm" variant="outline" onClick={handleVectorSourceDelete} isLoading={vectorSourceMutation.isPending}>
              Delete by Source
            </Button>
          </Box>

          <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
            <Heading size="sm" mb={3}>Job Status</Heading>
            <HStack spacing={3} mb={3} align="flex-end">
              <FormControl>
                <FormLabel fontSize="sm">Job ID</FormLabel>
                <Input size="sm" value={jobLookupId} onChange={(event: ChangeEvent<HTMLInputElement>) => setJobLookupId(event.target.value)} placeholder="Enter job ID" />
              </FormControl>
              <Button size="sm" onClick={handleJobLookup} isLoading={jobLookupMutation.isPending}>
                Refresh
              </Button>
            </HStack>
            {jobLookupResult ? (
              <Box as="pre" bg="gray.50" p={3} borderRadius="md" fontSize="xs">
                {JSON.stringify(jobLookupResult, null, 2)}
              </Box>
            ) : (
              <Text color="gray.500" fontSize="sm">Enter a job ID to load the latest status.</Text>
            )}
          </Box>
        </Stack>
      </Box>
    </Flex>
  );
}
