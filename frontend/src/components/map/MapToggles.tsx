import { LayersIcon, PauseIcon, PlayIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { MapControlContainer } from "@/components/ui/map"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Switch } from "@/components/ui/switch"
import { useMapToggles, type MapToggleKey } from "@/state/mapLayersStore"

const LAYER_ROWS: { key: MapToggleKey; label: string; desc: string }[] = [
  { key: "zones", label: "Zone risk fills", desc: "Severity colours at this replay tick" },
  { key: "alerts", label: "NWS alert polygons", desc: "Live watches and warnings" },
  { key: "radar", label: "Weather radar", desc: "Animated rain loop, past hour" },
  { key: "cyclones", label: "Cyclones + cone", desc: "Live NHC storms, track and cone" },
  { key: "wind", label: "Wind particles", desc: "Animated surface wind flow" },
  { key: "marineAqi", label: "Marine & air quality", desc: "Wave height and AQI badge" },
]

const ANIM_ROWS: { key: MapToggleKey; label: string; desc: string }[] = [
  { key: "pulse", label: "Pulsing alert zones", desc: "Zones on alert breathe" },
  { key: "spotlight", label: "Top-zone spotlight", desc: "Rank #1 gets a marching outline" },
  { key: "transitions", label: "Smooth transitions", desc: "Fade severity between ticks" },
]

/** Single toggle panel for every layer and animation on the map. */
export function MapToggles() {
  return (
    <MapControlContainer className="top-1 right-1">
      <Popover>
        <PopoverTrigger
          render={
            <Button
              type="button"
              variant="secondary"
              size="icon-sm"
              aria-label="Toggle map layers"
              title="Toggle map layers"
              className="border shadow-sm"
            />
          }
        >
          <LayersIcon />
        </PopoverTrigger>
        <PopoverContent align="end" side="bottom" className="z-1000 w-72">
          <ToggleSection title="Layers" rows={LAYER_ROWS} />
          <div className="mt-2 border-t pt-2">
            <ToggleSection title="Animations" rows={ANIM_ROWS} />
          </div>
        </PopoverContent>
      </Popover>
    </MapControlContainer>
  )
}

function ToggleSection({ title, rows }: { title: string; rows: typeof LAYER_ROWS }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="px-1 text-xs font-medium text-muted-foreground">{title}</div>
      {rows.map((r) => (
        <ToggleRow key={r.key} row={r} />
      ))}
    </div>
  )
}

function ToggleRow({ row }: { row: (typeof LAYER_ROWS)[number] }) {
  const checked = useMapToggles((s) => s[row.key])
  const toggle = useMapToggles((s) => s.toggle)
  const radarPlaying = useMapToggles((s) => s.radarPlaying)
  const set = useMapToggles((s) => s.set)
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1.5 hover:bg-muted/60">
      <span className="min-w-0 flex-1">
        <span className="block text-sm leading-tight">{row.label}</span>
        <span className="block truncate text-xs text-muted-foreground">{row.desc}</span>
      </span>
      {row.key === "radar" && checked && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={radarPlaying ? "Pause radar" : "Play radar"}
          title={radarPlaying ? "Pause radar" : "Play radar"}
          onClick={(e) => {
            e.preventDefault()
            set("radarPlaying", !radarPlaying)
          }}
        >
          {radarPlaying ? <PauseIcon /> : <PlayIcon />}
        </Button>
      )}
      <Switch checked={checked} onCheckedChange={() => toggle(row.key)} aria-label={row.label} />
    </label>
  )
}
