/** Types and legacy re-exports. Prefer EngineProvider + useEngineSelector. */
export type {
    AdviceEvent,
    ControlMessage,
    CostBreakdown,
    CostEvent,
    EngineSnapshot,
    EngineState,
    FeedItem,
    PerfEvent,
    RuntimeConfig,
} from "@/lib/engine-types";

export { EngineProvider, useEngineActions, useEngineSelector } from "@/lib/engine-provider";
