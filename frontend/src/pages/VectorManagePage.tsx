import { useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Heading,
  HStack,
  Input,
  NumberInput,
  NumberInputField,
  Radio,
  RadioGroup,
  Stack,
  Table,
  Tbody,
  Td,
  Th,
  Thead,
  Tr,
  Text,
  useToast,
} from "@chakra-ui/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { deleteVectorDoc, deleteVectorSource } from "../api/ingest";
import { queryVectorAll } from "../api/vector";

export function VectorManagePage() {
  const toast = useToast();
  const [mode, setMode] = useState<"id" | "source">("id");
  const [docId, setDocId] = useState("");
  const [source, setSource] = useState("");
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  const listQuery = useQuery({
    queryKey: ["vector-list"],
    queryFn: () => queryVectorAll(1000),
    staleTime: 30_000,
  });

  const records = listQuery.data ?? [];
  const totalPages = Math.max(1, Math.ceil(records.length / pageSize));
  const paged = useMemo(() => {
    const start = (page - 1) * pageSize;
    return records.slice(start, start + pageSize);
  }, [records, page, pageSize]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [totalPages, page]);

  const deleteById = useMutation({
    mutationFn: async (id: string) => deleteVectorDoc(id),
    onSuccess: () => {
      toast({ title: "Document deleted", status: "success" });
      listQuery.refetch();
    },
    onError: (e: any) => toast({ title: "Failed to delete", description: e?.message ?? String(e), status: "error" }),
  });

  const deleteBySource = useMutation({
    mutationFn: async (src: string) => deleteVectorSource(src),
    onSuccess: () => {
      toast({ title: "Source deleted", status: "success" });
      listQuery.refetch();
    },
    onError: (e: any) => toast({ title: "Failed to delete", description: e?.message ?? String(e), status: "error" }),
  });

  return (
    <Stack spacing={6} align="stretch">
      <Heading size="lg">Manage Vector DB Documents</Heading>
      <Text color="gray.600">Delete by ID or Source, and browse existing documents.</Text>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Stack spacing={4}>
          <FormControl>
            <FormLabel>Delete Mode</FormLabel>
            <RadioGroup value={mode} onChange={(v) => setMode(v as any)}>
              <HStack spacing={6}>
                <Radio value="id">By ID</Radio>
                <Radio value="source">By Source</Radio>
              </HStack>
            </RadioGroup>
          </FormControl>
          {mode === "id" ? (
            <HStack>
              <Input placeholder="Document ID" value={docId} onChange={(e) => setDocId(e.target.value)} />
              <Button
                colorScheme="red"
                onClick={() => docId.trim() && deleteById.mutate(docId.trim())}
                isLoading={deleteById.isPending}
              >
                Delete by ID
              </Button>
            </HStack>
          ) : (
            <HStack>
              <Input placeholder="Source (e.g. jira, ui_flow)" value={source} onChange={(e) => setSource(e.target.value)} />
              <Button
                colorScheme="red"
                onClick={() => source.trim() && deleteBySource.mutate(source.trim())}
                isLoading={deleteBySource.isPending}
              >
                Delete by Source
              </Button>
            </HStack>
          )}
        </Stack>
      </Box>

      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <HStack justify="space-between" mb={4}>
          <Heading size="md">Existing Docs</Heading>
          <HStack>
            <NumberInput size="sm" min={5} max={100} value={pageSize} onChange={(_, n) => setPageSize(n || 20)}>
              <NumberInputField />
            </NumberInput>
            <Text color="gray.500">per page</Text>
          </HStack>
        </HStack>
        {listQuery.isLoading ? (
          <Text color="gray.500">Loading…</Text>
        ) : records.length === 0 ? (
          <Text color="gray.500">No documents found in Vector DB.</Text>
        ) : (
          <>
            <Table size="sm" variant="striped">
              <Thead>
                <Tr>
                  <Th>ID</Th>
                  <Th>Source</Th>
                  <Th isNumeric>Meta Keys</Th>
                </Tr>
              </Thead>
              <Tbody>
                {paged.map((r) => (
                  <Tr key={r.id}>
                    <Td maxW="520px" isTruncated title={r.id}>{r.id}</Td>
                    <Td>{(r.metadata?.source as string) ?? ""}</Td>
                    <Td isNumeric>{Object.keys(r.metadata ?? {}).length}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
            <HStack mt={4} justify="space-between">
              <Button size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} isDisabled={page <= 1}>
                Prev
              </Button>
              <Text>
                Page {page} of {totalPages}
              </Text>
              <Button size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} isDisabled={page >= totalPages}>
                Next
              </Button>
            </HStack>
          </>
        )}
      </Box>
    </Stack>
  );
}
