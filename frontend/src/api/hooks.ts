import { useQuery } from "@tanstack/react-query"
import { api, type SnapshotQuery, type Weights } from "./client"

const STATIC_STALE = 5 * 60 * 1000

export function useRegions(event_id?: number) {
  return useQuery({
    queryKey: ["regions", event_id],
    queryFn: () => api.regions(event_id),
    staleTime: STATIC_STALE,
    retry: 1,
  })
}

export function useRegionZones(region_id: string | undefined, event_id?: number) {
  return useQuery({
    queryKey: ["region-zones", region_id, event_id],
    queryFn: () => api.regionZones(region_id!, event_id),
    enabled: region_id != null,
    staleTime: STATIC_STALE,
    retry: 1,
  })
}

export function useEvents() {
  return useQuery({
    queryKey: ["events"],
    queryFn: api.events,
    staleTime: STATIC_STALE,
    retry: 1,
  })
}

export function useZonePayload(zone_id: string | undefined, q: SnapshotQuery = {}) {
  return useQuery({
    queryKey: ["zone", zone_id, q.event_id, q.issue_ts],
    queryFn: () => api.zone(zone_id!, q),
    enabled: zone_id != null,
    retry: 1,
  })
}

export function useRanking(q: SnapshotQuery & Partial<Weights> = {}) {
  const { event_id, issue_ts, ...weights } = q
  return useQuery({
    queryKey: ["ranking", event_id, issue_ts, weights],
    queryFn: () => api.ranking(q),
    retry: 1,
  })
}

export function useMetrics(region_id: string | undefined, event_id?: number) {
  return useQuery({
    queryKey: ["metrics", region_id, event_id],
    queryFn: () => api.metrics(region_id!, event_id),
    enabled: region_id != null,
    staleTime: STATIC_STALE,
    retry: 1,
  })
}

