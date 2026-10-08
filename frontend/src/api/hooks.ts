import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { api, type SnapshotQuery, type Weights } from "./client"

/** Local-LLM briefing for the selected zone only; paused while the replay plays so the 3B model isn't flooded. */
export function useZoneBriefing(zone_id: string | undefined, q: SnapshotQuery & Partial<Weights>, enabled: boolean) {
  const { event_id, issue_ts, ...weights } = q
  return useQuery({
    queryKey: ["briefing", zone_id, event_id, issue_ts, weights],
    queryFn: () => api.zoneBriefing(zone_id!, q),
    enabled: enabled && zone_id != null && q.issue_ts != null,
    staleTime: Infinity,
    retry: 0,
  })
}

/** Live NWS/NHC hazard context. Refreshes every 5 min; never part of the replay or the model. */
export function useLiveContext() {
  return useQuery({ queryKey: ["live-context"], queryFn: api.context, refetchInterval: 5 * 60 * 1000, retry: 0 })
}

/** Alerts that have fired up to the current replay tick, newest first. */
export function useAlertFeed(session_id: string | undefined, upto: number) {
  return useQuery({
    queryKey: ["alerts", session_id, upto],
    queryFn: () => api.replayAlerts(session_id!, upto),
    enabled: session_id != null,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

/** Starts a replay session once per event and step; returns its tick timestamps. */
export function useReplay(event_id: number, step_h: number) {
  return useQuery({
    queryKey: ["replay", event_id, step_h],
    queryFn: () => api.replayStart(event_id, step_h),
    staleTime: Infinity,
    retry: 1,
  })
}

/** Every zone's payload at one tick, ranked under the given weights; keeps the old frame while the next loads. */
export function useTick(event_id: number, issue_ts: string | undefined, weights: Weights) {
  return useQuery({
    queryKey: ["tick", event_id, issue_ts, weights],
    queryFn: () => api.ranking({ event_id, issue_ts, ...weights }),
    enabled: issue_ts != null,
    placeholderData: keepPreviousData,
    retry: 1,
  })
}

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

