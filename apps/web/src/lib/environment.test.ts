import { describe, expect, it } from "vitest";

import { isPaymentSimulationEnabled } from "./environment";

describe("isPaymentSimulationEnabled", () => {
  it.each<[string | undefined, string, boolean]>([
    ["development", "production", true],
    ["test", "production", true],
    ["production", "development", false],
    ["staging", "development", false],
    [undefined, "production", false],
    [undefined, "development", true],
    [undefined, "test", true],
  ])(
    "with Jepret %s and Node %s returns %s",
    (jepretEnvironment, nodeEnvironment, expected) => {
      expect(
        isPaymentSimulationEnabled(jepretEnvironment, nodeEnvironment),
      ).toBe(expected);
    },
  );
});
