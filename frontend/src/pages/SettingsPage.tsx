import {
  Box,
  FormControl,
  FormLabel,
  Heading,
  Button,
  Select,
  Input,
  Stack,
  Text,
} from "@chakra-ui/react";

import { useSessionStore } from "../state/session";
import { useRef, useState } from "react";
import { uploadFile } from "../api/files";

export function SettingsPage() {
  const {
    frameworkRepoPath,
    frameworkBranch,
    frameworkCommitMessage,
    authToken,
    setFrameworkRepoPath,
    setFrameworkBranch,
    setFrameworkCommitMessage,
    setAuthToken,
  } = useSessionStore();

  const fileRef = useRef<HTMLInputElement | null>(null);
  const [target, setTarget] = useState<"uploads" | "framework-data">("framework-data");
  const [uploadResult, setUploadResult] = useState<string>("");

  const doUpload = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) return;
    try {
      const rel = await uploadFile(f, target, authToken, frameworkRepoPath || undefined);
      setUploadResult(rel);
    } catch (err: any) {
      setUploadResult(String(err?.message || err));
    }
  };

  return (
    <Stack spacing={6}>
      <Heading size="lg">Workspace Settings</Heading>
      <Text color="gray.600">
        Persist the defaults that previously lived in the Streamlit sidebar.
        These values will back the session preferences stored in the database
        when the migration is complete.
      </Text>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Stack spacing={4}>
          <FormControl>
            <FormLabel>Framework Repo Path</FormLabel>
            <Input
              value={frameworkRepoPath}
              onChange={(event) => setFrameworkRepoPath(event.target.value)}
            />
          </FormControl>
          <FormControl>
            <FormLabel>Auth Token</FormLabel>
            <Input value={authToken} onChange={(e) => setAuthToken(e.target.value)} placeholder="dev" />
          </FormControl>
          <FormControl>
            <FormLabel>Branch</FormLabel>
            <Input
              value={frameworkBranch}
              onChange={(event) => setFrameworkBranch(event.target.value)}
            />
          </FormControl>
          <FormControl>
            <FormLabel>Commit Message</FormLabel>
            <Input
              value={frameworkCommitMessage}
              onChange={(event) =>
                setFrameworkCommitMessage(event.target.value)
              }
            />
          </FormControl>
        </Stack>
      </Box>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>Upload Test Data</Heading>
        <Stack spacing={3}>
          <FormControl>
            <FormLabel>Target</FormLabel>
            <Select value={target} onChange={(e) => setTarget(e.target.value as any)}>
              <option value="framework-data">framework-data</option>
              <option value="uploads">uploads</option>
            </Select>
          </FormControl>
          <FormControl>
            <FormLabel>File</FormLabel>
            <Input type="file" ref={fileRef} />
          </FormControl>
          <Button onClick={doUpload}>Upload</Button>
          {uploadResult && (
            <Text color="gray.700">Saved: {uploadResult}</Text>
          )}
        </Stack>
      </Box>
    </Stack>
  );
}

