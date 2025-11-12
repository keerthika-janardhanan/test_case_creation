import { useMemo, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  Stack,
  Switch,
  Table,
  Tbody,
  Td,
  Text,
  Textarea,
  Th,
  Thead,
  Tr,
  useToast,
} from "@chakra-ui/react";
import { useMutation } from "@tanstack/react-query";

import { generateTestCases, generateTestCasesWithTemplate } from "../api/testCases";
import type { TestCaseRecord, TestCaseRequestPayload, TestCaseResponse } from "../api/testCases";

function base64ToBlob(b64: string, mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") {
  const binary = atob(b64);
  const len = binary.length;
  const buffer = new Uint8Array(len);
  for (let i = 0; i < len; i += 1) {
    buffer[i] = binary.charCodeAt(i);
  }
  return new Blob([buffer], { type: mime });
}

export function TestCasesPage() {
  const [story, setStory] = useState("");
  const [llmOnly, setLlmOnly] = useState(false);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [result, setResult] = useState<TestCaseResponse | null>(null);
  const [manualLoading, setManualLoading] = useState(false);
  const toast = useToast();

  const mutation = useMutation<TestCaseResponse, Error, TestCaseRequestPayload>({
    mutationFn: generateTestCases,
    onSuccess: (data) => {
      setResult(data);
      toast({ title: "Test cases generated", status: "success" });
    },
    onError: (error) => {
      setResult(null);
      toast({
        title: "Generation failed",
        description: error.message || "Unable to generate test cases",
        status: "error",
      });
    },
  });

  const handleSubmit = async () => {
    if (!story.trim()) {
      toast({
        title: "Story is required",
        status: "warning",
      });
      return;
    }
    setResult(null);
    if (templateFile) {
      try {
        setManualLoading(true);
        const data = await generateTestCasesWithTemplate(story, llmOnly, templateFile);
        setResult(data);
        toast({ title: "Generated with template", status: "success" });
      } catch (err: any) {
        setResult(null);
        toast({ title: "Generation failed", description: err?.message || String(err), status: "error" });
      } finally {
        setManualLoading(false);
      }
    } else {
      mutation.mutate({ story, llmOnly, asExcel: true });
    }
  };

  const handleDownload = () => {
    if (!result?.excel) {
      return;
    }
    const blob = base64ToBlob(result.excel);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "test-cases.xlsx";
    link.click();
    URL.revokeObjectURL(url);
  };

  const columns = useMemo(() => {
    if (!result?.records?.length) {
      return [];
    }
    return Object.keys(result.records[0]);
  }, [result]);

  const isGenerating = mutation.isPending || manualLoading;

  return (
    <Stack spacing={6} align="stretch">
      <Heading size="lg">Test Case Generator</Heading>
      <Text color="gray.600">
        Generate regression suites from Jira stories or refined flow context via the
        FastAPI backend. Results stream through the React Query mutation below.
      </Text>
      <Box as="form" bg="white" borderRadius="lg" p={6} boxShadow="sm" onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        handleSubmit();
      }}>
        <Stack spacing={4}>
          <FormControl id="testcases-story">
            <FormLabel>Story / Scenario</FormLabel>
            <Textarea
              id="testcases-story"
              value={story}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setStory(event.target.value)}
              minH="160px"
              placeholder="Paste Jira story, acceptance criteria, or flow keywords"
            />
          </FormControl>
          <FormControl id="template-upload">
            <FormLabel>Template File (optional, Excel .xlsx/.xls)</FormLabel>
            <Input
              type="file"
              accept=".xlsx,.xls,.json,.txt,.doc,.docx"
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                const f = e.target.files?.[0] || null;
                setTemplateFile(f);
              }}
            />
          </FormControl>
          <HStack justify="space-between">
            <Stack direction="row" spacing={3} align="center">
              <Switch
                isChecked={llmOnly}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setLlmOnly(event.target.checked)}
              />
              <Text>LLM-only (skip deterministic injection)</Text>
            </Stack>
            <Button
              type="submit"
              colorScheme="blue"
              isLoading={isGenerating}
            >
              Generate
            </Button>
          </HStack>
        </Stack>
      </Box>

      {result && (
        <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
          <HStack justify="space-between" mb={4} align="start">
            <Heading size="md">Generated Records</Heading>
            <Button onClick={handleDownload} isDisabled={!result.excel}>
              Download Excel
            </Button>
          </HStack>
          {columns.length ? (
            <Table size="sm" variant="striped">
              <Thead>
                <Tr>
                  {columns.map((column) => (
                    <Th key={column}>{column}</Th>
                  ))}
                </Tr>
              </Thead>
              <Tbody>
                {result.records.map((record: TestCaseRecord, idx: number) => (
                  <Tr key={`record-${idx}`}>
                    {columns.map((column) => (
                      <Td key={column}>{String(record[column] ?? "")}</Td>
                    ))}
                  </Tr>
                ))}
              </Tbody>
            </Table>
          ) : (
            <Text color="gray.500">No records returned.</Text>
          )}
        </Box>
      )}
    </Stack>
  );
}
