import { requestJson } from "../../shared/api/api";

export interface PublicProfile {
  profile: "adx" | "public-cosmos";
  partition?: string;
  transport?: string;
  coverage?: string;
}

export interface PublicRecord {
  id: string;
  resource_id: string;
  partition: string;
  kind: "incident" | "alarm" | "event";
  source: Record<string, string | number>;
  title: string;
  rule_version: string;
  event_refs: string[];
  timestamp: string;
  host: string;
  fields: Record<string, string>;
  entity_refs: Record<string, string>;
  derived: boolean;
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid public source object");
  return value as Record<string, unknown>;
}

function strings(value: unknown): Record<string, string> {
  const result = object(value ?? {});
  if (Object.values(result).some((item) => typeof item !== "string")) throw new Error("Invalid public source fields");
  return result as Record<string, string>;
}

function record(value: unknown): PublicRecord {
  const item = object(value);
  for (const key of ["id", "resource_id", "partition", "kind"]) {
    if (typeof item[key] !== "string" || !item[key]) throw new Error(`Missing public ${key}`);
  }
  if (!["incident", "alarm", "event"].includes(String(item.kind))) throw new Error("Unknown public record kind");
  const source = object(item.source);
  if (Object.values(source).some((value) => typeof value !== "string" && typeof value !== "number")) {
    throw new Error("Invalid public provenance");
  }
  const refs = item.event_refs ?? [];
  if (!Array.isArray(refs) || refs.some((value) => typeof value !== "string")) throw new Error("Invalid evidence references");
  return {
    id: item.id as string, resource_id: item.resource_id as string, partition: item.partition as string,
    kind: item.kind as PublicRecord["kind"], source: source as PublicRecord["source"],
    title: String(item.title ?? ""), rule_version: String(item.rule_version ?? ""), event_refs: refs as string[],
    timestamp: String(item.timestamp ?? ""), host: String(item.host ?? ""), fields: strings(item.fields),
    entity_refs: strings(item.entity_refs), derived: item.derived === true,
  };
}

async function list(path: string): Promise<PublicRecord[]> {
  const result = await requestJson<unknown>(path);
  if (!Array.isArray(result)) throw new Error("Invalid public record list");
  return result.map(record);
}

const query = (values: Record<string, string>) => new URLSearchParams(values).toString();
export const publicApi = {
  profile: async (): Promise<PublicProfile> => {
    const result = object(await requestJson<unknown>("/api/cyber/public/profile"));
    if (result.profile !== "adx" && result.profile !== "public-cosmos") throw new Error("Unknown source profile");
    if (result.profile === "public-cosmos" && typeof result.partition !== "string") throw new Error("Missing scenario partition");
    return result as unknown as PublicProfile;
  },
  cases: (partition: string) => list(`/api/cyber/public/cases?${query({ partition })}`),
  alarms: (partition: string, case_id: string) => list(`/api/cyber/public/alarms?${query({ partition, case_id })}`),
  evidence: (partition: string, resource_id: string) => list(`/api/cyber/public/evidence?${query({ partition, resource_id })}`),
  document: async (partition: string, id: string) => record(await requestJson<unknown>(
    `/api/cyber/public/document?${query({ partition, id })}`)),
};