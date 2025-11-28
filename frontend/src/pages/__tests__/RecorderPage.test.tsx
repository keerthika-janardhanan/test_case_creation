import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChakraProvider } from "@chakra-ui/react";

import { RecorderPage } from "../RecorderPage";

function renderRecorderPage() {
  const queryClient = new QueryClient();
  render(
    <ChakraProvider>
      <QueryClientProvider client={queryClient}>
        <RecorderPage />
      </QueryClientProvider>
    </ChakraProvider>,
  );
}

describe("RecorderPage", () => {
  it("renders recorder heading", () => {
    renderRecorderPage();
    expect(
      screen.getByRole("heading", { name: /Playwright Recorder/i }),
    ).toBeInTheDocument();
  });

  it("shows launch form inputs", () => {
    renderRecorderPage();
    expect(screen.getByLabelText(/Application URL/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Flow name/i)).toBeInTheDocument();
  });
});
