import type { ReactNode } from "react";
import { Box } from "@chakra-ui/react";

interface CardProps {
  children: ReactNode;
  title?: string;
  padding?: number | string;
}

export function Card({ children, padding = 6 }: CardProps) {
  return (
    <Box
      bg="white"
      borderRadius="xl"
      boxShadow="sm"
      borderWidth="1px"
      borderColor="gray.200"
      p={padding}
      transition="all 0.2s"
      _hover={{
        boxShadow: "md",
      }}
    >
      {children}
    </Box>
  );
}
