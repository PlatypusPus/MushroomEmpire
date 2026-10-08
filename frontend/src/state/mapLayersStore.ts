import { create } from "zustand"

/** Every map layer and animation is behind a toggle. Single source of truth
 * for the toggle panel; overlays subscribe to their own key. */
export type MapToggleKey =
  | "zones"
  | "alerts"
  | "radar"
  | "cyclones"
  | "wind"
  | "marineAqi"
  | "pulse"
  | "spotlight"
  | "transitions"

export type MapToggleState = Record<MapToggleKey, boolean> & {
  radarPlaying: boolean
  toggle: (key: MapToggleKey) => void
  set: (key: MapToggleKey | "radarPlaying", value: boolean) => void
}

export const useMapToggles = create<MapToggleState>()((set) => ({
  zones: true,
  alerts: true,
  radar: false,
  cyclones: true,
  wind: false,
  marineAqi: true,
  pulse: true,
  spotlight: true,
  transitions: true,
  radarPlaying: true,
  toggle: (key) => set((s) => ({ [key]: !s[key] }) as Partial<MapToggleState>),
  set: (key, value) => set({ [key]: value } as Partial<MapToggleState>),
}))
