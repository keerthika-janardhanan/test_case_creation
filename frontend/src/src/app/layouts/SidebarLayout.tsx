import type { ReactNode } from "react";
import { useState } from "react";

import { Box, Flex, Heading, Stack, Text, VStack, HStack, Collapse } from "@chakra-ui/react";
import { useLocation, NavLink as RouterNavLink } from "react-router-dom";

// Removed global repo settings; session store consumed only within specific pages now.

interface NavLinkConfig {
  label: string;
  to: string;
}

const NAV_LINKS: NavLinkConfig[] = [
  { label: "Recorder & Ingest", to: "/recorder" },
  { label: "Jira Ingestion", to: "/jira" },
  { label: "Website Ingestion", to: "/website" },
  { label: "Document Ingestion", to: "/documents" },
  { label: "Generate Test Cases", to: "/test-cases" },
  { label: "Test Script Generator", to: "/script-generator" },
  { label: "Vector Manage", to: "/vector-manage" },
];

interface SidebarLayoutProps {
  children: ReactNode;
}

export function SidebarLayout({ children }: SidebarLayoutProps) {
  const location = useLocation();
  // Repo path/branch/commit message removed from global header; page-level components access store directly where needed.
  const filteredLinks = NAV_LINKS;

  // Group the ingestion-related links under a dropdown titled "Vector Ingestion".
  const INGEST_PATHS = new Set(["/recorder", "/jira", "/website", "/documents"]);
  const ingestLinks = filteredLinks.filter((l) => INGEST_PATHS.has(l.to));
  const otherLinks = filteredLinks.filter((l) => !INGEST_PATHS.has(l.to));
  const isIngestActive = ingestLinks.some((link) => location.pathname.startsWith(link.to));
  const [ingestOpen, setIngestOpen] = useState<boolean>(true);

  return (
    <Flex minH="100vh" bg="gray.50">
      <Box
        as="nav"
        w={{ base: "240px", xl: "260px" }}
        bg="gray.900"
        color="white"
        px={6}
        py={8}
      >
        <Heading size="md" mb={8}>
          Test Artifact Suite
        </Heading>
        <Stack spacing={5}></Stack>
        <VStack spacing={2} align="stretch" mt={10}>
          {/* Vector Ingestion dropdown */}
          <Box>
            <HStack
              as="button"
              onClick={() => setIngestOpen((o) => !o)}
              w="100%"
              justifyContent="space-between"
              px={3}
              py={2}
              borderRadius="md"
              bg={isIngestActive ? "blue.500" : "transparent"}
              color={isIngestActive ? "white" : "gray.200"}
              _hover={{ bg: isIngestActive ? "blue.600" : "gray.800" }}
            >
              <Text fontSize="sm" fontWeight="semibold">Vector Ingestion</Text>
              <Text fontSize="sm">{ingestOpen ? "▼" : "▶"}</Text>
            </HStack>
            <Collapse in={ingestOpen} animateOpacity>
              <VStack spacing={1} align="stretch" mt={1} ml={2}>
                {ingestLinks.map((link) => {
                  const isActive = location.pathname.startsWith(link.to);
                  return (
                    <Box
                      as={RouterNavLink}
                      key={link.to}
                      to={link.to}
                      px={3}
                      py={2}
                      borderRadius="md"
                      fontSize="sm"
                      fontWeight="medium"
                      bg={isActive ? "blue.500" : "transparent"}
                      color={isActive ? "white" : "gray.200"}
                      _hover={{ bg: isActive ? "blue.600" : "gray.800" }}
                    >
                      {link.label}
                    </Box>
                  );
                })}
              </VStack>
            </Collapse>
          </Box>

          {/* Other links remain top-level */}
          {otherLinks.map((link) => {
            const isActive = location.pathname.startsWith(link.to);
            return (
              <Box
                as={RouterNavLink}
                key={link.to}
                to={link.to}
                px={3}
                py={2}
                borderRadius="md"
                fontSize="sm"
                fontWeight="medium"
                bg={isActive ? "blue.500" : "transparent"}
                color={isActive ? "white" : "gray.200"}
                _hover={{ bg: isActive ? "blue.600" : "gray.800" }}
              >
                {link.label}
              </Box>
            );
          })}
        </VStack>
      </Box>
      <Flex direction="column" flex="1">
        {/* Global header inputs removed: repo settings now live only on the Test Script Generator page */}
        <Box as="header" borderBottomWidth="1px" borderColor="gray.200" bg="white" px={{ base: 6, md: 10 }} py={4}>
          <Text fontSize="sm" color="gray.600">Test Artifact Suite</Text>
        </Box>
        <Box as="main" flex="1" px={{ base: 6, md: 10 }} py={10}>
          {children}
        </Box>
      </Flex>
    </Flex>
  );
}
