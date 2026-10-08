import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useMemo } from "react"

import { DEFAULT_WEIGHTS, useReplayStore } from "@/state/replayStore"
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

export const STEP_H = 3 // replay frame every 3 h of the event

/** Everything the replay pages share: ticks, zone names, the current tick's payloads and the alert feed.
 * React Query de-duplicates, so the dashboard, alerts page and sidebar badge all read the same requests. */
export function useReplayData({ tunable = false }: { tunable?: boolean } = {}) {
  // Only the Response priority page uses the slider weights; everywhere else ranks with the fixed defaults.
  const { eventId, tick, weights: tuned } = useReplayStore()
  const weights = tunable ? tuned : DEFAULT_WEIGHTS
  const regions = useRegions(eventId)
  const region = regions.data?.[0]
  const zones = useRegionZones(region?.id, eventId)
  const replay = useReplay(eventId, STEP_H)
  const ticks = replay.data?.ticks ?? []
  const payloads = useTick(eventId, ticks[tick], weights)
  const alerts = useAlertFeed(replay.data?.session_id, tick)
  const names = useMemo(() => new Map((zones.data ?? []).map((z) => [z.id, z.name])), [zones.data])
  return {
    region, zones: zones.data ?? [], ticks, now: ticks[tick] as string | undefined, names,
    rows: payloads.data ?? [], feed: alerts.data ?? [],
    error: [regions, zones, replay, payloads].find((q) => q.error)?.error,
  }
}

/** Live NWS/NHC hazard context. Refreshes every 5 min; never part of the replay or the model. */
export function useLiveContext() {
  return useQuery({ queryKey: ["live-context"], queryFn: api.context, refetchInterval: 5 * 60 * 1000, retry: 0 })
}

/** Live environmental map overlays (alert polygons, cones, radar, marine/AQI, wind). Overlay-only. */
export function useEnvLayers() {
  return useQuery({ queryKey: ["env-layers"], queryFn: api.env, refetchInterval: 5 * 60 * 1000, retry: 0 })
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

