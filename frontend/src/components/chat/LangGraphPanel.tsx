import { useMemo } from "react";
import {
  GitBranch, Search, Sparkles, MessageCircle,
  Play, CheckCircle2, X, HelpCircle,
} from "lucide-react";
import type { GraphState, GraphNodeStatus } from "../../providers/WebSocketProvider";

interface LangGraphPanelProps {
  graphState: GraphState;
  onClose: () => void;
}

interface NodeDef {
  id: string;
  label: string;
  icon: React.ElementType;
  description: string;
}

const NODE_DEFS: Record<string, NodeDef> = {
  router: {
    id: "router",
    label: "Router",
    icon: GitBranch,
    description: "Classifies intent and media type",
  },
  retrieve: {
    id: "retrieve",
    label: "Retrieve",
    icon: Search,
    description: "Hybrid search in vector database",
  },
  generate_retrieve: {
    id: "generate_retrieve",
    label: "Generate",
    icon: Sparkles,
    description: "Generates response with context",
  },
  reask_user: {
    id: "reask_user",
    label: "Ask for details",
    icon: HelpCircle,
    description: "Retrieval quality too low",
  },
  generate_general: {
    id: "generate_general",
    label: "General Answer",
    icon: MessageCircle,
    description: "Generates a general response",
  },
};

const statusColors: Record<GraphNodeStatus, string> = {
  idle:      "border-gray-700 bg-gray-900/50",
  active:    "border-purple-500 bg-purple-950/40 shadow-[0_0_20px_rgba(168,85,247,0.15)]",
  completed: "border-emerald-500/60 bg-emerald-950/20",
  error:     "border-red-500/60 bg-red-950/20",
};
const dotColors: Record<GraphNodeStatus, string> = {
  idle:      "bg-gray-600",
  active:    "bg-purple-400",
  completed: "bg-emerald-400",
  error:     "bg-red-400",
};
const iconColors: Record<GraphNodeStatus, string> = {
  idle:      "text-gray-500",
  active:    "text-purple-400",
  completed: "text-emerald-400",
  error:     "text-red-400",
};

// ---------------------------------------------------------------------------
// NodeCard
// ---------------------------------------------------------------------------

function NodeCard({ def, status, output, isInPath }: {
  def: NodeDef;
  status: GraphNodeStatus;
  output?: Record<string, any>;
  isInPath: boolean;
}) {
  const Icon = def.icon;
  const dimmed = !isInPath && status === "idle";

  return (
    <div className={`
      relative rounded-lg border px-3 py-2.5 transition-all duration-500
      ${statusColors[status]}
      ${dimmed ? "opacity-35" : "opacity-100"}
    `}>
      <div className="flex items-center gap-2.5">
        <div className={`relative flex-shrink-0 ${iconColors[status]}`}>
          <Icon className="w-4 h-4" />
          {status === "active" && (
            <span className="absolute -inset-1 rounded-full bg-purple-500/20 animate-ping" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">{def.label}</span>
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors duration-500
              ${dotColors[status]} ${status === "active" ? "animate-pulse" : ""}`}
            />
          </div>
          <p className="text-[11px] text-gray-500 leading-tight mt-0.5">{def.description}</p>
        </div>
      </div>

      {output && Object.keys(output).length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-800/60 space-y-1">
          {output.decision && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Decision</span>
              <span className={`ml-2 text-xs font-mono font-semibold
                ${output.decision === "RETRIEVE" ? "text-blue-400" : "text-amber-400"}`}>
                {output.decision}
              </span>
            </div>
          )}
          {output.media_type && output.media_type !== "any" && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Media</span>
              <span className="ml-2 text-xs font-mono text-purple-300">{output.media_type}</span>
            </div>
          )}
          {output.documents_count !== undefined && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">Docs</span>
              <span className="ml-2 text-xs font-mono text-blue-300">{output.documents_count} found</span>
            </div>
          )}
          {output.needs_reask && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-amber-500/70 font-medium">
                Low quality — asking for details
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edge helpers
// ---------------------------------------------------------------------------

function EdgeLine({ active, completed }: { active: boolean; completed: boolean }) {
  return (
    <div className="flex justify-center -my-px">
      <div className="relative w-px h-5">
        <div className={`absolute inset-0 w-px transition-colors duration-500
          ${completed ? "bg-emerald-500/40" : active ? "bg-purple-500/60" : "bg-gray-700/50"}`}
        />
        {active && <div className="absolute inset-0 w-px bg-purple-400/80 animate-pulse" />}
      </div>
    </div>
  );
}

/**
 * Router split: 2 branches
 *   left  → retrieve path   (RETRIEVE)
 *   right → generate_general (GENERAL)
 */
function RouterSplit({ decision, pathSet }: {
  decision: string | null;
  pathSet: Set<string>;
}) {
  const leftActive  = pathSet.has("retrieve") || pathSet.has("generate_retrieve") || pathSet.has("reask_user");
  const rightActive = pathSet.has("generate_general");

  const color = (on: boolean) => on ? "stroke-emerald-500/40" : "stroke-gray-700/50";

  return (
    <div className="relative -my-px">
      <svg viewBox="0 0 200 30" className="w-full h-6 block" preserveAspectRatio="none">
        {/* center-top → left-bottom */}
        <path d="M 100 0 Q 100 15, 45 30"  fill="none"
          className={`${color(leftActive)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {/* center-top → right-bottom */}
        <path d="M 100 0 Q 100 15, 155 30" fill="none"
          className={`${color(rightActive)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      {decision && (
        <>
          <span className="absolute left-1 bottom-0 text-[9px] font-mono text-blue-400/70">RETRIEVE</span>
          <span className="absolute right-1 bottom-0 text-[9px] font-mono text-amber-400/70">GENERAL</span>
        </>
      )}
    </div>
  );
}

/**
 * Retrieve sub-split: 2 branches
 *   left  → generate_retrieve  (quality ok)
 *   right → reask_user         (quality poor)
 */
function RetrieveSplit({ pathSet }: { pathSet: Set<string> }) {
  const leftActive  = pathSet.has("generate_retrieve");
  const rightActive = pathSet.has("reask_user");

  const color = (on: boolean) => on ? "stroke-emerald-500/40" : "stroke-gray-700/50";

  return (
    <div className="relative -my-px">
      <svg viewBox="0 0 160 28" className="w-full h-5 block" preserveAspectRatio="none">
        <path d="M 80 0 Q 80 14, 35 28"  fill="none"
          className={`${color(leftActive)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <path d="M 80 0 Q 80 14, 125 28" fill="none"
          className={`${color(rightActive)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="absolute left-1 bottom-0 text-[9px] font-mono text-emerald-400/60">OK</span>
      <span className="absolute right-1 bottom-0 text-[9px] font-mono text-amber-400/60">POOR</span>
    </div>
  );
}

/**
 * Final merge: all terminal nodes converge to END
 *   far-left  → generate_retrieve
 *   mid-left  → reask_user
 *   right     → generate_general
 */
function FinalMerge({ pathSet }: { pathSet: Set<string> }) {
  const a = pathSet.has("generate_retrieve");
  const b = pathSet.has("reask_user");
  const c = pathSet.has("generate_general");

  const color = (on: boolean) => on ? "stroke-emerald-500/40" : "stroke-gray-700/50";

  return (
    <div className="-my-px">
      <svg viewBox="0 0 200 30" className="w-full h-6 block" preserveAspectRatio="none">
        <path d="M 35  0 Q 35  15, 100 30" fill="none"
          className={`${color(a)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <path d="M 80  0 Q 80  15, 100 30" fill="none"
          className={`${color(b)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        <path d="M 155 0 Q 155 15, 100 30" fill="none"
          className={`${color(c)} transition-all duration-500`}
          strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

/*
 * Actual graph topology rendered:
 *
 *              START
 *                │
 *             [router]
 *            ╱        ╲
 *       RETRIEVE      GENERAL
 *          │                  ╲
 *       [retrieve]        [generate_general]
 *        ╱     ╲                    │
 *       OK     POOR                 │
 *      ╱           ╲               │
 * [generate_retrieve] [reask_user]  │
 *        ╲           ╱             │
 *          ╲       ╱               │
 *              END ←───────────────╯
 */
const LangGraphPanel = ({ graphState, onClose }: LangGraphPanelProps) => {
  const { nodes, executionPath, isRunning } = graphState;
  const pathSet  = useMemo(() => new Set(executionPath), [executionPath]);
  const decision = nodes.router?.output?.decision ?? null;

  const nodeStatus = (id: string): GraphNodeStatus => nodes[id]?.status ?? "idle";
  const nodeOutput = (id: string) => nodes[id]?.output;

  const isRetrievePath   = pathSet.has("retrieve") || pathSet.has("generate_retrieve") || pathSet.has("reask_user");
  const isGeneralPath    = pathSet.has("generate_general");
  const anyTerminalDone  = pathSet.has("generate_retrieve") || pathSet.has("reask_user") || pathSet.has("generate_general");

  return (
    <div className="h-full flex flex-col bg-gray-950 border-l border-gray-800">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full transition-colors duration-300
            ${isRunning ? "bg-purple-400 animate-pulse" : "bg-gray-600"}`}
          />
          <h3 className="text-sm font-semibold text-gray-200">LangGraph Flow</h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        <div className="max-w-[300px] mx-auto">

          {/* START */}
          <div className="flex justify-center mb-0">
            <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all duration-500
              ${isRunning || executionPath.length > 0
                ? "border-emerald-500/50 text-emerald-400 bg-emerald-950/20"
                : "border-gray-700 text-gray-500 bg-gray-900/50"}`}>
              <Play className="w-3 h-3" />
              Start
            </div>
          </div>

          {/* START → router */}
          <EdgeLine
            active={nodeStatus("router") === "active"}
            completed={pathSet.has("router")}
          />

          {/* Router */}
          <NodeCard
            def={NODE_DEFS.router}
            status={nodeStatus("router")}
            output={nodeOutput("router")}
            isInPath={pathSet.has("router") || isRunning}
          />

          {/* Router split: RETRIEVE (left) vs GENERAL (right) */}
          <RouterSplit decision={decision} pathSet={pathSet} />

          {/* Two top-level columns */}
          <div className="grid grid-cols-2 gap-2">

            {/* ── Left column: retrieve path ── */}
            <div>
              {/* retrieve node */}
              <NodeCard
                def={NODE_DEFS.retrieve}
                status={nodeStatus("retrieve")}
                output={nodeOutput("retrieve")}
                isInPath={isRetrievePath}
              />

              {/* retrieve sub-split: generate_retrieve (left) vs reask_user (right) */}
              <RetrieveSplit pathSet={pathSet} />

              {/* Two sub-columns inside the left column */}
              <div className="grid grid-cols-2 gap-1">
                <NodeCard
                  def={NODE_DEFS.generate_retrieve}
                  status={nodeStatus("generate_retrieve")}
                  output={nodeOutput("generate_retrieve")}
                  isInPath={pathSet.has("generate_retrieve")}
                />
                <NodeCard
                  def={NODE_DEFS.reask_user}
                  status={nodeStatus("reask_user")}
                  output={nodeOutput("reask_user")}
                  isInPath={pathSet.has("reask_user")}
                />
              </div>
            </div>

            {/* ── Right column: general path ── */}
            <div className="flex flex-col">
              <NodeCard
                def={NODE_DEFS.generate_general}
                status={nodeStatus("generate_general")}
                output={nodeOutput("generate_general")}
                isInPath={isGeneralPath}
              />
              {/* Spacer so right column aligns with the sub-row on the left */}
              <div className="flex-1" />
            </div>
          </div>

          {/* All terminal nodes → END */}
          <FinalMerge pathSet={pathSet} />

          {/* END */}
          <div className="flex justify-center mt-0">
            <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all duration-500
              ${anyTerminalDone
                ? "border-emerald-500/50 text-emerald-400 bg-emerald-950/20"
                : "border-gray-700 text-gray-500 bg-gray-900/50"}`}>
              <CheckCircle2 className="w-3 h-3" />
              End
            </div>
          </div>

          {/* Execution log */}
          {executionPath.length > 0 && (
            <div className="mt-6 pt-4 border-t border-gray-800/60">
              <h4 className="text-[11px] uppercase tracking-wider text-gray-500 font-medium mb-2">
                Execution Path
              </h4>
              <div className="flex flex-wrap gap-1">
                {executionPath.map((node, i) => (
                  <span
                    key={`${node}-${i}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-gray-800/60 text-gray-400"
                  >
                    <span className="text-gray-600">{i + 1}.</span>
                    {node}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LangGraphPanel;