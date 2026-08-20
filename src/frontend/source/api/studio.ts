import { http } from "@/api/client";
import type { PublishedFlowCodeOut } from "@/types";

export async function listStudioProfiles(): Promise<{ id: string; code: string; name: string }[]> {
  const { data } = await http.get<{ id: string; code: string; name: string }[]>("/studio/profiles", {
    params: { limit: 50 },
  });
  return data;
}

export async function listPublishedFlowCodes(): Promise<PublishedFlowCodeOut[]> {
  const { data } = await http.get<PublishedFlowCodeOut[]>("/studio/flows/published-codes");
  return data;
}

export async function listStudioFlows(): Promise<{ id: string; code: string; name: string; version: number }[]> {
  const { data } = await http.get<{ id: string; code: string; name: string; version: number }[]>(
    "/studio/flows",
    { params: { limit: 50, status: "published" } },
  );
  return data;
}
