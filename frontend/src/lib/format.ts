export function money(
  value: string | null | undefined,
  currency = "USD",
  precision = 2,
): string {
  if (value === null || value === undefined) return "Not available";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(Number(value));
}
export function date(value: string) {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
export const originLabel: Record<string, string> = {
  synthetic_fixture: "Synthetic fixture",
  benchmark: "Benchmark data",
  local_observation: "Local observation",
  aws_observation: "AWS observation",
};

export function memory(value: number | null | undefined) {
  return value == null ? "Unknown" : `${(value / 1024).toLocaleString()} GiB`;
}
export function cpu(value: number | null | undefined) {
  return value == null ? "Unknown" : `${value / 1024} vCPU`;
}
export function human(value: string) {
  return value.replaceAll("_", " ");
}
