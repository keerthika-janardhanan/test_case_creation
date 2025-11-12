import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent } from "react";

import {
  Box,
  Button,
  Code,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Image,
  Input,
  List,
  ListItem,
  Stack,
  Stat,
  StatLabel,
  StatNumber,
  Text,
  useToast,
} from "@chakra-ui/react";
import { useMutation } from "@tanstack/react-query";

import { finalizeRecorderBySession, startRecorder, stopRecorder, getRecorderStatus, buildArtifactUrl } from "../api/recorder";
import { getJob } from "../api/jobs";
import type { JobDetail } from "../api/jobs";
// types in api/recorder are inferred where needed
import { useRecorderStream } from "../hooks/useRecorderStream";
// import { useJobStatus } from "../hooks/useJobStatus";

export function RecorderPage() {
  const [recorderUrl, setRecorderUrl] = useState("https://example.com");
  const [recorderFlowName, setRecorderFlowName] = useState("recorder-session");
  // const [launchJobId, setLaunchJobId] = useState<string | null>(null);
  const [stopSessionId, setStopSessionId] = useState("");
  // const [stopJobId, setStopJobId] = useState<string | null>(null);
  // Active session id is captured from Start response
  const [jobLookupId, setJobLookupId] = useState("");
  const [jobLookupResult, setJobLookupResult] = useState<JobDetail | null>(null);
  const [statusResult, setStatusResult] = useState<{ status: string; artifacts: Record<string, string>; files: string[] } | null>(null);
  // Recorder options now internal defaults; UI keeps minimal inputs
  const [timeoutSec, setTimeoutSec] = useState<number>(0);
  const toast = useToast();

  const activeSessionId = useMemo(() => {
    const trimmed = stopSessionId.trim();
    return trimmed ? trimmed : null;
  }, [stopSessionId]);

  // Legacy queue flow no longer used

  const stopMutation = useMutation<{ status: string }, Error, string>({
    mutationFn: stopRecorder,
    onSuccess: (data) => {
      toast({ title: "Stop issued", description: data.status, status: "info" });
    },
    onError: (error) => {
      toast({ title: "Failed to stop session", description: error.message, status: "error" });
    },
  });

  const jobLookupMutation = useMutation<JobDetail, Error, string>({
    mutationFn: getJob,
    onSuccess: (data) => {
      setJobLookupResult(data);
    },
    onError: (error) => {
      toast({ title: "Job lookup failed", description: error.message, status: "error" });
      setJobLookupResult(null);
    },
  });

  // const launchJobStatus = useJobStatus(launchJobId);
  // const stopJobStatus = useJobStatus(stopJobId);

  const { events, status } = useRecorderStream(activeSessionId);

  // Legacy handlers removed

  const handleStartNew = async () => {
    try {
      const res = await startRecorder({
        url: recorderUrl.trim(),
        sessionName: recorderFlowName.trim() || undefined,
        options: {
          flowName: recorderFlowName.trim() || undefined,
          timeout: timeoutSec && timeoutSec > 0 ? timeoutSec : undefined,
        },
      });
      setStopSessionId((prev) => prev || res.sessionId);
      toast({ title: "Recorder started", description: `Session ${res.sessionId}`, status: "success" });
    } catch (err: any) {
      toast({ title: "Start failed", description: String(err?.message || err), status: "error" });
    }
  };

  const handleStopNew = async () => {
    if (!stopSessionId.trim()) {
      toast({ title: "Session ID required", status: "warning" });
      return;
    }
    try {
      const res = await stopRecorder(stopSessionId.trim());
      toast({ title: "Stop issued", description: res.status, status: "info" });
    } catch (err: any) {
      toast({ title: "Stop failed", description: String(err?.message || err), status: "error" });
    }
  };

  const refreshStatus = async () => {
    const id = (stopSessionId || "").trim();
    if (!id) return;
    try {
      const res = await getRecorderStatus(id);
      setStatusResult(res);
    } catch {}
  };

  const finalizeBySession = async () => {
    const id = (stopSessionId || "").trim();
    if (!id) return;
    try {
      const res = await finalizeRecorderBySession(id);
      toast({ title: "Finalized & Ingested", description: res.autoIngest.status, status: res.autoIngest.status === "success" ? "success" : res.autoIngest.status === "error" ? "error" : "info" });
      try {
        const stats: any = (res.autoIngest.result as any)?.ingest_stats;
        if (stats && typeof stats.added === "number") {
          toast({ title: "Vector DB", description: `Steps added: ${stats.added}`, status: "success" });
        }
      } catch {}
    } catch {}
  };

  // Auto-finalize when recorder session completes or is stopped (via websocket events)
  useEffect(() => {
    if (!events.length) return;
    const last = events[events.length - 1] as any;
    const t = (last?.type || last?.event || "").toString();
    if (["launch-completed", "launch-stopped", "auto-finalized"].includes(t)) {
      finalizeBySession();
      refreshStatus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  const handleJobLookup = () => {
    if (!jobLookupId.trim()) {
      toast({ title: "Job ID required", status: "warning" });
      return;
    }
    jobLookupMutation.mutate(jobLookupId.trim());
  };

  return (
    <Stack spacing={6} align="stretch">
      <Heading size="lg">Playwright Recorder</Heading>
      <Text color="gray.600">
        Launch and monitor recorder jobs, finalise captured sessions, and stream live telemetry through the FastAPI backend.
      </Text>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>
          Launch Recorder Session
        </Heading>
        <Stack spacing={4}>
          <FormControl id="recorder-flow-name-top">
            <FormLabel>Flow name</FormLabel>
            <Input
              id="recorder-flow-name-top"
              value={recorderFlowName}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setRecorderFlowName(event.target.value)}
              placeholder="playwright-recorded-flow"
            />
          </FormControl>
          <FormControl id="recorder-url">
            <FormLabel>Application URL</FormLabel>
            <Input
              id="recorder-url"
              value={recorderUrl}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setRecorderUrl(event.target.value)}
              placeholder="https://example.com"
            />
          </FormControl>
          <HStack spacing={4}>
            <FormControl maxW="220px">
              <FormLabel>Auto-stop (seconds)</FormLabel>
              <Input type="number" value={timeoutSec} onChange={(e) => setTimeoutSec(Number(e.target.value) || 0)} />
            </FormControl>
          </HStack>
          <HStack>
            <Button onClick={handleStartNew} colorScheme="blue">Start</Button>
          </HStack>
        </Stack>
      </Box>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>
          Stop Recorder Session
        </Heading>
        <Stack spacing={3}>
          <Text>Active Session: <Code>{activeSessionId ?? "-"}</Code></Text>
          <Button onClick={handleStopNew} isDisabled={!activeSessionId} isLoading={stopMutation.isPending}>Stop</Button>
        </Stack>
      </Box>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>
          Session Status & Artifacts
        </Heading>
        <HStack align="flex-end" spacing={3} mb={3}>
          <Button onClick={refreshStatus}>Refresh</Button>
        </HStack>
        {statusResult ? (
          <Stack spacing={3}>
            <Text>Status: <Code>{statusResult.status}</Code></Text>
            {/* Inline preview and quick links */}
            {(() => {
              const resolvedSessionId = (stopSessionId || "").trim();
              const latest = (statusResult.artifacts || ({} as any)).latestScreenshot as string | undefined;
              const har = (statusResult.artifacts || ({} as any)).har as string | undefined;
              const trace = (statusResult.artifacts || ({} as any)).trace as string | undefined;
              if (!resolvedSessionId) return null;
              return (
                <HStack align="flex-start" spacing={6}>
                  {latest ? (
                    <Box>
                      <Text fontWeight="semibold" mb={2}>Latest screenshot</Text>
                      <a href={buildArtifactUrl(resolvedSessionId, latest)} target="_blank" rel="noreferrer">
                        <Image
                          src={buildArtifactUrl(resolvedSessionId, latest)}
                          alt="Latest screenshot"
                          maxW="280px"
                          borderRadius="md"
                          boxShadow="sm"
                        />
                      </a>
                    </Box>
                  ) : null}
                  <Box>
                    <Text fontWeight="semibold" mb={2}>Quick artifacts</Text>
                    <List spacing={1}>
                      {trace ? (
                        <ListItem>
                          <a href={buildArtifactUrl(resolvedSessionId, trace)} target="_blank" rel="noreferrer">trace.zip</a>
                        </ListItem>
                      ) : null}
                      {har ? (
                        <ListItem>
                          <a href={buildArtifactUrl(resolvedSessionId, har)} target="_blank" rel="noreferrer">network.har</a>
                        </ListItem>
                      ) : null}
                    </List>
                  </Box>
                </HStack>
              );
            })()}
            {statusResult.artifacts && (
              <Box>
                <Text fontWeight="semibold">Artifacts</Text>
                <List mt={2} spacing={1}>
                  {Object.entries(statusResult.artifacts).map(([key, val]) => (
                    <ListItem key={key}>
                      <a href={buildArtifactUrl(stopSessionId || "", val)} target="_blank" rel="noreferrer">
                        {key}: {val}
                      </a>
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}
            {statusResult.files?.length ? (
              <Box>
                <Text fontWeight="semibold">Files</Text>
                <List mt={2} spacing={1}>
                  {statusResult.files.map((f) => (
                    <ListItem key={f}>{f}</ListItem>
                  ))}
                </List>
              </Box>
            ) : null}
          </Stack>
        ) : null}
      </Box>

      {/* Finalize flow is automatic; keep custom events as advanced (optional) */}

      <HStack spacing={4} align="stretch">
        <Stat flex="1" bg="white" borderRadius="lg" p={4} boxShadow="sm">
          <StatLabel>Active session ID</StatLabel>
          <StatNumber>{activeSessionId ?? "-"}</StatNumber>
        </Stat>
        <Stat flex="1" bg="white" borderRadius="lg" p={4} boxShadow="sm">
          <StatLabel>Stream status</StatLabel>
          <StatNumber textTransform="capitalize">{status}</StatNumber>
        </Stat>
        <Stat flex="1" bg="white" borderRadius="lg" p={4} boxShadow="sm">
          <StatLabel>Captured events</StatLabel>
          <StatNumber>{events.length}</StatNumber>
        </Stat>
      </HStack>

      {/* Auto-ingest handled on backend; summary toasts appear on completion */}

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>
          Job Status Lookup
        </Heading>
        <HStack spacing={4} mb={4} align="flex-end">
          <FormControl id="recorder-job-id">
            <FormLabel>Job ID</FormLabel>
            <Input
              id="recorder-job-id"
              value={jobLookupId}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setJobLookupId(event.target.value)}
              placeholder="Enter job ID"
            />
          </FormControl>
          <Button onClick={handleJobLookup} isLoading={jobLookupMutation.isPending}>
            Refresh
          </Button>
        </HStack>
        {jobLookupResult ? (
          <Box as="pre" bg="gray.50" p={4} borderRadius="md">
            {JSON.stringify(jobLookupResult, null, 2)}
          </Box>
        ) : (
          <Text color="gray.500">Enter a job ID to fetch status.</Text>
        )}
      </Box>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>
          Live Event Stream
        </Heading>
        {events.length === 0 ? (
          <Text color="gray.500">No events yet. Queue a job or finalise a session to begin streaming.</Text>
        ) : (
          <Stack spacing={3} maxH="360px" overflowY="auto">
            {events.map((event, index) => (
              <Box
                key={`event-${index}`}
                borderLeftWidth="4px"
                borderLeftColor={event.level === "error" ? "red.400" : event.level === "warning" ? "orange.400" : "green.400"}
                bg="gray.50"
                p={3}
                borderRadius="md"
              >
                <Text fontWeight="semibold">{event.message ?? "(no message)"}</Text>
                <Text fontSize="sm" color="gray.600">
                  {JSON.stringify(event, null, 2)}
                </Text>
              </Box>
            ))}
          </Stack>
        )}
      </Box>
    </Stack>
  );
}
