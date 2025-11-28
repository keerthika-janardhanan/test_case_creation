import { Box, Button, FormControl, FormLabel, Heading, HStack, Input, Stack, Text, Textarea } from "@chakra-ui/react";
import { useState } from "react";
import { apiClient } from "../api/client";

interface VectorRecord {
  id?: string;
  content: string;
  metadata: Record<string, unknown>;
}

export function VectorSearchPage() {
  const [query, setQuery] = useState("");
  const [where, setWhere] = useState("{\n  \"type\": \"recorder_refined\"\n}");
  const [topK, setTopK] = useState(5);
  const [results, setResults] = useState<VectorRecord[]>([]);
  const [error, setError] = useState<string>("");

  const run = async () => {
    setError("");
    try {
      const parsedWhere = where.trim() ? JSON.parse(where) : undefined;
      const { data } = await apiClient.post<{ results: VectorRecord[] }>("/vector/query", {
        query,
        topK,
        where: parsedWhere,
      });
      setResults(data.results || []);
    } catch (err: any) {
      setError(String(err?.message || err));
      setResults([]);
    }
  };

  return (
    <Stack spacing={6}>
      <Heading size="lg">Vector Search</Heading>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Stack spacing={4}>
          <FormControl>
            <FormLabel>Query</FormLabel>
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Create Supplier" />
          </FormControl>
          <HStack>
            <FormControl>
              <FormLabel>Top K</FormLabel>
              <Input type="number" value={topK} onChange={(e) => setTopK(parseInt(e.target.value || "5", 10))} />
            </FormControl>
            <FormControl>
              <FormLabel>Where (JSON)</FormLabel>
              <Textarea value={where} onChange={(e) => setWhere(e.target.value)} rows={6} fontFamily="monospace" />
            </FormControl>
          </HStack>
          <Button onClick={run} colorScheme="blue">Search</Button>
          {error && <Text color="red.500">{error}</Text>}
          {results.length > 0 ? (
            <Stack spacing={4}>
              {results.map((r, idx) => (
                <Box key={r.id || idx} bg="gray.50" p={4} borderRadius="md" borderWidth="1px" borderColor="gray.200">
                  <Text fontSize="sm" color="gray.600">ID: {r.id || "(none)"}</Text>
                  <Text mt={1} fontWeight="semibold">Content</Text>
                  <Box as="pre" whiteSpace="pre-wrap" mt={1}>{String(r.content).slice(0, 2000)}</Box>
                  <Text mt={2} fontWeight="semibold">Metadata</Text>
                  <Box as="pre" mt={1}>{JSON.stringify(r.metadata || {}, null, 2)}</Box>
                </Box>
              ))}
            </Stack>
          ) : (
            <Text color="gray.500">No results.</Text>
          )}
        </Stack>
      </Box>
    </Stack>
  );
}
