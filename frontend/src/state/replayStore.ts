import { create } from "zustand"

import type { Weights } from "@/api/client"

export const DEFAULT_WEIGHTS: Weights = {
  probability: 0.3, severity: 0.2, urgency: 0.25, exposure: 0.1, vulnerable: 0.15, uncertainty: 0,
}

interface ReplayState {
  mode: "live" | "replay"
  eventId: number
  tick: number
  playing: boolean
  selectedZone: string | null
  weights: Weights
  setMode: (m: "live" | "replay") => void
  setEvent: (id: number) => void
  setTick: (i: number) => void
  setPlaying: (p: boolean) => void
  select: (zoneId: string | null) => void
  setWeight: (k: keyof Weights, v: number) => void
}

export const useReplayStore = create<ReplayState>((set) => ({
  mode: "replay", // the dashboard opens on the storm replay; live official hazards are one click away
  eventId: 8, // 2023 Nov Extreme Rain Event: last option in the event picker
  tick: 0,
  playing: false,
  selectedZone: null,
  weights: DEFAULT_WEIGHTS,
  setMode: (mode) => set({ mode, playing: false, selectedZone: null }),
  setEvent: (eventId) => set({ eventId, mode: "replay", tick: 0, playing: false, selectedZone: null }),
  setTick: (tick) => set({ tick }),
  setPlaying: (playing) => set({ playing }),
  select: (selectedZone) => set({ selectedZone }),
  setWeight: (k, v) => set((s) => ({ weights: { ...s.weights, [k]: v } })),
}))
