import { Box, Button, FormControl, FormLabel, Heading, Input, Stack, Textarea, useToast } from "@chakra-ui/react";
import { useRef, useState } from "react";
import { streamTrial } from "../api/trial";
import { useSessionStore } from "../state/session";

export function TrialRunsPage() {
  const toast = useToast();
  const { authToken, frameworkRepoPath } = useSessionStore();
  const [spec, setSpec] = useState("tests/sample.spec.ts");
  const [logs, setLogs] = useState("");
  const [streaming, setStreaming] = useState(false);
  const ctrlRef = useRef<AbortController | null>(null);

  const start = async () => {
    setLogs("");
    setStreaming(true);
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;
    try {
      await streamTrial(spec, authToken, true, frameworkRepoPath || undefined, (evt) => {
        if (evt?.message) {
          setLogs((prev) => prev + evt.message + "\n");
        }
      }, ctrl.signal);
    } catch (err: any) {
      toast({ status: "error", title: "Trial stream failed", description: String(err?.message || err) });
    } finally {
      setStreaming(false);
    }
  };

  const stop = () => {
    ctrlRef.current?.abort();
    setStreaming(false);
  };

  return (
    <Stack spacing={6}>
      <Heading size="lg">Trial Runs</Heading>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <FormControl>
          <FormLabel>Spec Path</FormLabel>
          <Input value={spec} onChange={(e) => setSpec(e.target.value)} placeholder="tests/slug.spec.ts" />
        </FormControl>
        <Stack direction="row" spacing={3} mt={4}>
          <Button onClick={start} colorScheme="blue" isDisabled={streaming}>Start Stream</Button>
          <Button onClick={stop} isDisabled={!streaming}>Stop</Button>
        </Stack>
        <Textarea value={logs} onChange={(e) => setLogs(e.target.value)} rows={16} mt={4} fontFamily="monospace" />
      </Box>
    </Stack>
  );
}

