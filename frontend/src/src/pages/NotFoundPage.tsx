import { Button, Heading, Stack, Text } from "@chakra-ui/react";
import { useNavigate } from "react-router-dom";

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <Stack spacing={4} align="flex-start">
      <Heading size="lg">Page not found</Heading>
      <Text color="gray.600">
        The requested view does not exist. Choose a destination from the
        sidebar or return to the agentic assistant.
      </Text>
      <Button onClick={() => navigate("/agentic")} colorScheme="blue">
        Go to Agentic Chat
      </Button>
    </Stack>
  );
}

