import type { ReactNode } from "react";

import { ChakraProvider, ColorModeScript, extendTheme } from "@chakra-ui/react";
import type { ThemeConfig } from "@chakra-ui/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const config: ThemeConfig = {
  initialColorMode: "light",
  useSystemColorMode: false,
};

const theme = extendTheme({
  config,
  fonts: {
    heading: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    body: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  colors: {
    brand: {
      50: "#e6f2ff",
      100: "#baddff",
      200: "#8dc8ff",
      300: "#5fb3ff",
      400: "#319eff",
      500: "#0084ff",
      600: "#0070e0",
      700: "#005ab8",
      800: "#004590",
      900: "#003068",
    },
  },
  styles: {
    global: {
      body: {
        bg: "gray.50",
        color: "gray.800",
      },
    },
  },
  components: {
    Button: {
      defaultProps: {
        colorScheme: "brand",
      },
      variants: {
        solid: {
          _hover: {
            transform: "translateY(-1px)",
            boxShadow: "md",
          },
          transition: "all 0.2s",
        },
      },
    },
    Card: {
      baseStyle: {
        container: {
          bg: "white",
          boxShadow: "sm",
          borderRadius: "lg",
          borderWidth: "1px",
          borderColor: "gray.200",
        },
      },
    },
  },
});

interface Props {
  children: ReactNode;
}

export function AppProviders({ children }: Props) {
  return (
    <ChakraProvider theme={theme}>
      <ColorModeScript initialColorMode={theme.config.initialColorMode} />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ChakraProvider>
  );
}
