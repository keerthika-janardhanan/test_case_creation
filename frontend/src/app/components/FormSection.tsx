import type { ReactNode } from "react";
import { Box, Heading, VStack } from "@chakra-ui/react";

interface FormSectionProps {
  title?: string;
  children: ReactNode;
  spacing?: number;
}

export function FormSection({ title, children, spacing = 4 }: FormSectionProps) {
  return (
    <Box
      bg="white"
      borderRadius="xl"
      boxShadow="sm"
      borderWidth="1px"
      borderColor="gray.200"
      p={6}
      transition="all 0.2s"
      _hover={{
        boxShadow: "md",
      }}
    >
      {title && (
        <Heading size="md" mb={4} color="gray.700" fontWeight="600">
          {title}
        </Heading>
      )}
      <VStack spacing={spacing} align="stretch">
        {children}
      </VStack>
    </Box>
  );
}
