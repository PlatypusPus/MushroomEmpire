import { create } from "zustand"

import type { Weights } from "@/api/client"

export const DEFAULT_WEIGHTS: Weights = {
  probability: 0.3, severity: 0.2, urgency: 0.25, exposure: 0.1, vulnerable: 0.15, uncertainty: 0,
}

interface ReplayState {
  eventId: number
  tick: number
  playing: boolean
  selectedZone: string | null
  weights: Weights
  setEvent: (id: number) => void
  setTick: (i: number) => void
  setPlaying: (p: boolean) => void
  select: (zoneId: string | null) => void
  setWeight: (k: keyof Weights, v: number) => void
}

export const useReplayStore = create<ReplayState>((set) => ({
  eventId: 5, // Hurricane Nicole, Nov 2022 (ROOT_CONTEXT 20.2a)
  tick: 0,
  playing: false,
  selectedZone: null,
  weights: DEFAULT_WEIGHTS,
  setEvent: (eventId) => set({ eventId, tick: 0, playing: false, selectedZone: null }),
  setTick: (tick) => set({ tick }),
  setPlaying: (playing) => set({ playing }),
  select: (selectedZone) => set({ selectedZone }),
  setWeight: (k, v) => set((s) => ({ weights: { ...s.weights, [k]: v } })),
}))
