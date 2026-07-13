import { useQuery } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueryProvider } from "./query-provider";

function Probe() {
  const query = useQuery({ queryKey: ["probe"], queryFn: async () => "siap" });
  return <span>{query.data ?? "memuat"}</span>;
}

describe("QueryProvider", () => {
  it("provides a query client", async () => {
    render(
      <QueryProvider>
        <Probe />
      </QueryProvider>,
    );
    expect(await screen.findByText("siap")).toBeInTheDocument();
  });
});
