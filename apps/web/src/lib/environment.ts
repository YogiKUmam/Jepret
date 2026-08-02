export function isPaymentSimulationEnabled(
  jepretEnvironment: string | undefined = process.env
    .NEXT_PUBLIC_JEPRET_ENVIRONMENT,
  nodeEnvironment: string | undefined = process.env.NODE_ENV,
) {
  if (jepretEnvironment !== undefined) {
    return jepretEnvironment === "development" || jepretEnvironment === "test";
  }

  return nodeEnvironment === "development" || nodeEnvironment === "test";
}
