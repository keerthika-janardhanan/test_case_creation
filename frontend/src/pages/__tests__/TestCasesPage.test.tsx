import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChakraProvider } from "@chakra-ui/react";

import { TestCasesPage } from "../TestCasesPage";

function renderTestCasesPage() {
  const queryClient = new QueryClient();
  render(
    <ChakraProvider>
      <QueryClientProvider client={queryClient}>
        <TestCasesPage />
      </QueryClientProvider>
    </ChakraProvider>,
  );
}

describe("TestCasesPage", () => {
  it("renders generator heading", () => {
    renderTestCasesPage();
    expect(
      screen.getByRole("heading", { name: /Test Case Generator/i }),
    ).toBeInTheDocument();
  });

  it("includes story input", () => {
    renderTestCasesPage();
    expect(screen.getByLabelText(/Story/i)).toBeInTheDocument();
  });
});
