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
        w={{ base: "260px", xl: "280px" }}
        bg="linear-gradient(180deg, #1a202c 0%, #2d3748 100%)"
        color="white"
        px={6}
        py={8}
        boxShadow="xl"
        position="relative"
        _after={{
          content: '""',
          position: "absolute",
          right: 0,
          top: 0,
          bottom: 0,
          width: "1px",
          bg: "whiteAlpha.100",
        }}
      >
        <Heading size="lg" mb={2} fontWeight="bold" letterSpacing="tight">
          Test Artifact Suite
        </Heading>
        <Text fontSize="xs" color="whiteAlpha.700" mb={10}>
          Automated Test Generation Platform
        </Text>
        <Stack spacing={5}></Stack>
        <VStack spacing={2} align="stretch" mt={6}>
          {/* Vector Ingestion dropdown */}
          <Box>
            <HStack
              as="button"
              onClick={() => setIngestOpen((o) => !o)}
              w="100%"
              justifyContent="space-between"
              px={4}
              py={3}
              borderRadius="lg"
              bg={isIngestActive ? "whiteAlpha.200" : "transparent"}
              color={isIngestActive ? "white" : "whiteAlpha.800"}
              _hover={{ bg: isIngestActive ? "whiteAlpha.300" : "whiteAlpha.100" }}
              transition="all 0.2s"
            >
              <Text fontSize="sm" fontWeight="600">Vector Ingestion</Text>
              <Text fontSize="xs">{ingestOpen ? "▼" : "▶"}</Text>
            </HStack>
            <Collapse in={ingestOpen} animateOpacity>
              <VStack spacing={1} align="stretch" mt={2} ml={3}>
                {ingestLinks.map((link) => {
                  const isActive = location.pathname.startsWith(link.to);
                  return (
                    <Box
                      as={RouterNavLink}
                      key={link.to}
                      to={link.to}
                      px={4}
                      py={2.5}
                      borderRadius="md"
                      fontSize="sm"
                      fontWeight="500"
                      bg={isActive ? "brand.500" : "transparent"}
                      color={isActive ? "white" : "whiteAlpha.800"}
                      _hover={{ 
                        bg: isActive ? "brand.600" : "whiteAlpha.100",
                        transform: "translateX(4px)",
                      }}
                      transition="all 0.2s"
                      borderLeftWidth="2px"
                      borderLeftColor={isActive ? "brand.300" : "transparent"}
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
                px={4}
                py={3}
                borderRadius="lg"
                fontSize="sm"
                fontWeight="600"
                bg={isActive ? "brand.500" : "transparent"}
                color={isActive ? "white" : "whiteAlpha.800"}
                _hover={{ 
                  bg: isActive ? "brand.600" : "whiteAlpha.100",
                  transform: "translateX(4px)",
                }}
                transition="all 0.2s"
                borderLeftWidth="3px"
                borderLeftColor={isActive ? "brand.300" : "transparent"}
              >
                {link.label}
              </Box>
            );
          })}
        </VStack>
      </Box>
      <Flex direction="column" flex="1">
        {/* Global header inputs removed: repo settings now live only on the Test Script Generator page */}
        <Box 
          as="header" 
          borderBottomWidth="1px" 
          borderColor="gray.200" 
          bg="white" 
          px={{ base: 6, md: 10 }} 
          py={6}
          boxShadow="sm"
        >
          <HStack spacing={4}>
            <Box 
              w="8px" 
              h="8px" 
              borderRadius="full" 
              bg="green.400"
              boxShadow="0 0 0 3px rgba(72, 187, 120, 0.2)"
            />
            <Text fontSize="lg" fontWeight="600" color="gray.700">
              Test Artifact Suite
            </Text>
          </HStack>
        </Box>
        <Box as="main" flex="1" px={{ base: 6, md: 10 }} py={8} bg="gray.50">
          {children}
        </Box>
      </Flex>
    </Flex>
  );
}
