import { Box, Heading, Stack, Text } from "@chakra-ui/react";

export function GitOpsPage() {
  return (
    <Stack spacing={6}>
      <Heading size="lg">Git Operations</Heading>
      <Text color="gray.600">
        Manage generated files, review diffs, and push curated commits. The UI
        will integrate with the Git push service surfaced by the backend agent
        endpoints.
      </Text>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={3}>
          Roadmap
        </Heading>
        <Text color="gray.600">
          - Show pending file list from refined flows and agent payloads.
          <br />- Inline diff viewer to approve updates before pushing.
          <br />- Commit summary panel with branch selection and status badges.
        </Text>
      </Box>
    </Stack>
  );
}

