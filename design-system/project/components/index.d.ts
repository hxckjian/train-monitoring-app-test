// Nebula Wayside — component types.
// Documentation, not a compile target. Every factory returns a detached HTMLElement;
// the caller appends it. Nothing here reads from the network or mutates global state.

export type State = "ok" | "watch" | "alert" | "unknown";

export interface StatusChipOptions {
  /** Which of the four states. An unrecognised value renders as `unknown`. */
  state: State;
  /** Overrides the default word. Use only when the subsystem has a better term. */
  label?: string;
  /** The object, not the reasoning: "Car 03", "Cycle 41". */
  detail?: string;
}
export function StatusChip(options: StatusChipOptions): HTMLElement;

export interface VerdictCardOptions {
  state: State;
  /** Shown small and uppercase beside the chip: "ACV", "Door", "Rail", "SHM". */
  subsystem?: string;
  title?: string;
  /** One plain sentence. No metric names. */
  meaning?: string;
  /** One signature visual. A result needing two figures needs two cards. */
  figure?: HTMLElement;
  /** Imperative and time-bounded. */
  action?: string;
  /** Mono provenance line: score, split method, model version. */
  evidence?: string;
}
export function VerdictCard(options: VerdictCardOptions): HTMLElement;

export interface DamageGaugeOptions {
  value: number;
  /** Defaults to 1. Leave it there for cumulative damage. */
  max?: number;
  /** Draws a hard rule; 1.0 is failure under the linear cumulative-damage rule. */
  threshold?: number;
  label?: string;
  caption?: string;
  /** Decimal places on the displayed value. Default 3. */
  precision?: number;
}
export function DamageGauge(options: DamageGaugeOptions): HTMLElement;

export interface Segment {
  id?: string;
  /** Seconds from the stream origin. */
  start: number;
  end: number;
  status: State;
}
export interface DoorTimelineOptions {
  segments: Segment[];
  /** Total stream length in seconds. Defaults to the last segment end. */
  duration?: number;
  label?: string;
  caption?: string;
}
export function DoorTimeline(options: DoorTimelineOptions): HTMLElement;

export interface AxleCell {
  /** 1-based car number. */
  car: number;
  /** 1-based axle-box position. Odd positions are Side I, even are Side II. */
  position: number;
  /** Normalised 0–1. Normalise for train speed upstream. */
  value: number;
}
export interface AxleGridOptions {
  cells: AxleCell[];
  /** Defaults to 8. A missing cell draws as no-data, not as zero. */
  cars?: number;
  label?: string;
  caption?: string;
}
export function AxleGrid(options: AxleGridOptions): HTMLElement;

export interface RankedCar {
  /** The two-digit identifier from the file's own headers: "03", never "Car 3". */
  id: string;
  score: number;
}
export interface CarRankOptions {
  /** Already sorted best-first. The component does not sort. */
  cars: RankedCar[];
  label?: string;
  caption?: string;
}
export function CarRank(options: CarRankOptions): HTMLElement;

export const STATES: Record<State, { word: string; glyph: string; token: string }>;
