import { useMemo } from "react";
import {
  GitBranch, Search, Sparkles, MessageCircle, ScanSearch,
  Play, CheckCircle2, X, HelpCircle, Activity
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
    label: "Intent Router",
    icon: GitBranch,
    description: "RETRIEVE vs GENERAL on standalone query",
  },
  contextualize: {
    id: "contextualize",
    label: "Contextualize",
    icon: ScanSearch,
    description: "Merges history into one query (runs first)",
  },
  retrieve: {
    id: "retrieve",
    label: "Vector Retrieval",
    icon: Search,
    description: "Hybrid DB similarity search",
  },
  generate_retrieve: {
    id: "generate_retrieve",
    label: "Context Synth",
    icon: Sparkles,
    description: "RAG response generation",
  },
  reask_user: {
    id: "reask_user",
    label: "Clarification",
    icon: HelpCircle,
    description: "Fires on low confidence",
  },
  generate_general: {
    id: "generate_general",
    label: "Base LLM",
    icon: MessageCircle,
    description: "Zero-shot general response",
  },
};

// Refined, lower-intensity theme for a calmer diagnostic surface.
const theme = {
  idle: {
    card: "border-slate-800/80 bg-slate-950/75 hover:border-slate-700/80 hover:bg-slate-900/80",
    icon: "text-slate-500 bg-slate-900/80",
    text: "text-slate-400",
    dot: "bg-slate-600",
  },
  active: {
    card: "border-sky-400/20 bg-slate-900/85 shadow-[0_18px_40px_-32px_rgba(56,189,248,0.55)] ring-1 ring-sky-300/10",
    icon: "text-sky-100 bg-sky-500/10",
    text: "text-slate-100",
    dot: "bg-sky-300",
  },
  completed: {
    card: "border-indigo-300/20 bg-slate-900/80",
    icon: "text-indigo-200 bg-indigo-500/10",
    text: "text-slate-200",
    dot: "bg-indigo-300",
  },
  error: {
    card: "border-rose-300/25 bg-slate-900/80",
    icon: "text-rose-200 bg-rose-500/10",
    text: "text-slate-100",
    dot: "bg-rose-300",
  },
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
  const currentTheme = theme[status];

  return (
    <div className={`
      relative overflow-visible rounded-lg border px-3 py-3 transition-all duration-300
      ${currentTheme.card}
      ${dimmed ? "opacity-55" : "opacity-100"}
    `}>
      {status === "active" && (
        <div className="pointer-events-none absolute inset-y-3 left-0 w-px rounded-full bg-sky-300/40" />
      )}

      <div className="relative flex items-start gap-3 min-w-0">
        <div className={`relative flex-shrink-0 rounded-md p-2 transition-colors duration-300 ${currentTheme.icon}`}>
          <Icon className="w-4 h-4" />
        </div>
        
        <div className="flex-1 min-w-0 pt-0.5">
          <div className="flex items-start justify-between gap-2">
            <span className={`text-[13px] font-medium leading-snug break-words ${currentTheme.text}`}>
              {def.label}
            </span>
            <span className={`h-2 w-2 rounded-full flex-shrink-0 mt-1 transition-colors duration-300
              ${currentTheme.dot} ${status === "active" ? "opacity-90" : "opacity-70"}`}
            />
          </div>
          <p className="mt-1 text-[11px] leading-5 text-slate-500 break-words hyphens-auto">
            {def.description}
          </p>
        </div>
      </div>

      {output && Object.keys(output).length > 0 && (
        <div className="relative mt-3 grid grid-cols-2 gap-2.5 border-t border-slate-800/80 pt-3">
          {output.decision && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Route</span>
              <span className={`w-max rounded-md border px-1.5 py-0.5 font-mono text-[11px]
                ${output.decision === "RETRIEVE" ? "border-sky-400/20 bg-sky-500/[0.08] text-sky-200" :
                  "border-amber-300/20 bg-amber-500/[0.08] text-amber-200"}`}>
                {output.decision}
              </span>
            </div>
          )}
          {output.media_type && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Media</span>
              <span
                className={`w-max rounded-md border px-1.5 py-0.5 font-mono text-[11px]
                ${output.media_type === "any"
                  ? "border-slate-700 bg-slate-900/80 text-slate-300"
                  : "border-violet-300/20 bg-violet-500/[0.08] text-violet-200"}`}
              >
                {output.media_type}
              </span>
            </div>
          )}
          {output.rewritten_question && (
            <div className="flex flex-col gap-0.5 col-span-2">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Rewrite</span>
              <span className="rounded-md border border-emerald-300/20 bg-emerald-500/[0.08] px-1.5 py-1 text-[11px] leading-snug text-emerald-100 break-words">
                {output.rewritten_question}
              </span>
            </div>
          )}
          {output.rewrote === false && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Status</span>
              <span className="w-max rounded-md border border-slate-700 bg-slate-900/80 px-1.5 py-0.5 font-mono text-[11px] text-slate-300">
                unchanged
              </span>
            </div>
          )}
          {output.documents_count !== undefined && (
            <div className="flex flex-col gap-0.5 col-span-2">
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Vectors</span>
              <div className="flex w-max items-center gap-1.5 rounded-md border border-sky-300/20 bg-sky-500/[0.08] px-1.5 py-0.5 font-mono text-[11px] text-sky-200">
                <Activity className="w-3 h-3" />
                {output.documents_count} hits found
              </div>
            </div>
          )}
          {output.needs_reask && (
            <div className="col-span-2 mt-1">
              <div className="flex items-center gap-1.5 rounded-md border border-rose-300/20 bg-rose-500/[0.08] px-2 py-1 text-[10px] font-medium uppercase tracking-[0.14em] text-rose-200">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-300" />
                Sub-optimal Match
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quiet SVG edge helpers
// ---------------------------------------------------------------------------

const getEdgeStyle = (active: boolean, completed: boolean) => {
  if (active) return "stroke-sky-300/65";
  if (completed) return "stroke-indigo-300/35";
  return "stroke-slate-800";
};

function EdgeLine({ active, completed }: { active: boolean; completed: boolean }) {
  return (
    <div className="flex justify-center -my-px relative z-0">
      <div className="relative h-5 w-px">
        <div className={`absolute inset-0 transition-all duration-300
          ${completed ? "bg-indigo-300/35" : active ? "bg-sky-300/60" : "bg-slate-800"}`}
        />
      </div>
    </div>
  );
}

/** Tall vertical edge so the general path (Base LLM) visually reaches the merge above Terminate. */
function EdgeTrunk({ active, completed, className }: { active: boolean; completed: boolean; className?: string }) {
  return (
    <div className={`flex flex-1 flex-col items-center min-h-0 py-0 -my-px relative z-0 ${className ?? ""}`}>
      <div className="relative w-px flex-1 min-h-[8px]">
        <div
          className={`absolute inset-0 transition-all duration-300
          ${completed ? "bg-indigo-300/35" : active ? "bg-sky-300/60" : "bg-slate-800"}`}
        />
      </div>
    </div>
  );
}

function RouterSplit({ decision, pathSet }: { decision: string | null; pathSet: Set<string>; }) {
  const leftActive =
    pathSet.has("retrieve") ||
    pathSet.has("generate_retrieve") ||
    pathSet.has("reask_user");
  const rightActive = pathSet.has("generate_general");

  return (
    <div className="relative -my-px z-0">
      <svg viewBox="0 0 200 36" className="w-full h-8 block" preserveAspectRatio="none">
        <path d="M 100 0 Q 100 18, 53 36" fill="none"
          className={`${getEdgeStyle(decision === "RETRIEVE" && !leftActive, leftActive)} transition-all duration-300`}
          strokeWidth={leftActive ? "1.75" : "1.25"} vectorEffect="non-scaling-stroke" />
        <path d="M 100 0 Q 100 18, 153 36" fill="none"
          className={`${getEdgeStyle(decision === "GENERAL" && !rightActive, rightActive)} transition-all duration-300`}
          strokeWidth={rightActive ? "1.75" : "1.25"} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function FinalMerge({ pathSet }: { pathSet: Set<string> }) {
  // Geometry matches grid `1fr / 0.9fr`: left-column center ≈53, right ≈153 (viewBox 200).
  const leftBranch = pathSet.has("generate_retrieve") || pathSet.has("reask_user");
  const rightBranch = pathSet.has("generate_general");

  return (
    <div className="-my-px z-0 relative">
      <svg viewBox="0 0 200 36" className="w-full h-8 block" preserveAspectRatio="none">
        <path d="M 53 0 Q 53 18, 100 36" fill="none"
          className={`${getEdgeStyle(false, leftBranch)} transition-all duration-300`}
          strokeWidth={leftBranch ? "1.75" : "1.25"} vectorEffect="non-scaling-stroke" />
        <path d="M 153 0 Q 153 18, 100 36" fill="none"
          className={`${getEdgeStyle(false, rightBranch)} transition-all duration-300`}
          strokeWidth={rightBranch ? "1.75" : "1.25"} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

const LangGraphPanel = ({ graphState, onClose }: LangGraphPanelProps) => {
  const { nodes, executionPath, isRunning } = graphState;
  const pathSet  = useMemo(() => new Set(executionPath), [executionPath]);
  const decision = nodes.router?.output?.decision ?? null;

  const nodeStatus = (id: string): GraphNodeStatus => nodes[id]?.status ?? "idle";
  const nodeOutput = (id: string) => nodes[id]?.output;

  const isRetrievePath =
    pathSet.has("retrieve") ||
    pathSet.has("generate_retrieve") ||
    pathSet.has("reask_user");
  const isGeneralPath = pathSet.has("generate_general");
  const anyTerminalDone  = pathSet.has("generate_retrieve") || pathSet.has("reask_user") || pathSet.has("generate_general");

  return (
    <div className="relative flex h-full flex-col overflow-hidden border-l border-slate-800/80 bg-[#05070b] text-white font-sans">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(56,189,248,0.08),transparent_38%),radial-gradient(circle_at_bottom,rgba(99,102,241,0.05),transparent_34%)]" />

      {/* Header */}
      <div className="relative z-10 flex items-center justify-between border-b border-slate-800/80 bg-slate-950/70 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full border border-slate-800 bg-slate-900/80">
            <div className={`h-2.5 w-2.5 rounded-full transition-colors duration-300
              ${isRunning ? "bg-sky-300" : "bg-slate-600"}`} />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-[0.02em] text-slate-100">Nexus Graph</h3>
            <p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">Live execution state</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-md border border-slate-800 bg-slate-900/70 p-1.5 text-slate-400 transition-colors hover:border-slate-700 hover:bg-slate-900 hover:text-slate-200"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="relative z-10 flex-1 overflow-y-auto px-4 py-8 custom-scrollbar">
        <div className="max-w-[min(100%,380px)] mx-auto">

          {/* START */}
          <div className="flex justify-center mb-0 relative z-10">
            <div className={`flex items-center gap-2 rounded-full border px-4 py-1.5 text-[11px] font-medium uppercase tracking-[0.18em] transition-all duration-300
              ${isRunning || executionPath.length > 0
                ? "border-sky-300/25 bg-sky-500/[0.08] text-sky-200"
                : "border-slate-800 bg-slate-900/70 text-slate-400"}`}>
              <Play className="w-3.5 h-3.5" />
              Init
            </div>
          </div>

          <EdgeLine
            active={nodeStatus("contextualize") === "active"}
            completed={pathSet.has("contextualize")}
          />

          <NodeCard
            def={NODE_DEFS.contextualize}
            status={nodeStatus("contextualize")}
            output={nodeOutput("contextualize")}
            isInPath={pathSet.has("contextualize") || isRunning}
          />

          <EdgeLine
            active={nodeStatus("router") === "active"}
            completed={pathSet.has("router")}
          />

          <NodeCard
            def={NODE_DEFS.router}
            status={nodeStatus("router")}
            output={nodeOutput("router")}
            isInPath={pathSet.has("router") || isRunning}
          />

          <RouterSplit decision={decision} pathSet={pathSet} />

          {/* Two top-level columns */}
          <div className="grid grid-cols-[1fr_0.9fr] gap-3 relative z-10 items-stretch">
            {/* Left: retrieve path (after router RETRIEVE) */}
            <div className="flex flex-col min-w-0">
              <EdgeLine
                active={nodeStatus("retrieve") === "active"}
                completed={pathSet.has("retrieve")}
              />
              <NodeCard
                def={NODE_DEFS.retrieve}
                status={nodeStatus("retrieve")}
                output={nodeOutput("retrieve")}
                isInPath={isRetrievePath}
              />
              <EdgeLine
                active={
                  nodeStatus("generate_retrieve") === "active" ||
                  nodeStatus("reask_user") === "active"
                }
                completed={pathSet.has("generate_retrieve") || pathSet.has("reask_user")}
              />

              <div className="grid grid-cols-1 gap-2 min-w-0">
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

            {/* Right: general path — trunk links Base LLM down to FinalMerge / Terminate */}
            <div className="flex flex-col min-h-0 min-w-0 h-full">
              <EdgeLine
                active={nodeStatus("generate_general") === "active"}
                completed={pathSet.has("generate_general")}
              />
              <NodeCard
                def={NODE_DEFS.generate_general}
                status={nodeStatus("generate_general")}
                output={nodeOutput("generate_general")}
                isInPath={isGeneralPath}
              />
              <EdgeTrunk
                active={nodeStatus("generate_general") === "active"}
                completed={pathSet.has("generate_general")}
              />
            </div>
          </div>

          <FinalMerge pathSet={pathSet} />

          {/* END */}
          <div className="flex justify-center mt-0 relative z-10">
            <div className={`flex items-center gap-2 rounded-full border px-4 py-1.5 text-[11px] font-medium uppercase tracking-[0.18em] transition-all duration-300
              ${anyTerminalDone
                ? "border-indigo-300/25 bg-indigo-500/[0.08] text-indigo-200"
                : "border-slate-800 bg-slate-900/70 text-slate-500"}`}>
              <CheckCircle2 className="w-3.5 h-3.5" />
              Terminate
            </div>
          </div>

          {/* Execution Log */}
          {executionPath.length > 0 && (
            <div className="mt-8 rounded-lg border border-slate-800/80 bg-slate-950/75 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="h-3.5 w-3.5 text-slate-400" />
                <h4 className="text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
                  Trace Log
                </h4>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {executionPath.map((node, i) => (
                  <div key={`${node}-${i}`} className="flex items-center gap-1.5">
                    <span className="inline-flex items-center rounded-md border border-slate-800 bg-slate-900/90 px-2 py-1 text-[10px] font-mono text-slate-300">
                      <span className="mr-1.5 text-slate-500">{i + 1}</span>
                      {node}
                    </span>
                    {i < executionPath.length - 1 && (
                      <span className="text-[10px] text-slate-700">→</span>
                    )}
                  </div>
                ))}
                {isRunning && (
                  <span className="inline-flex items-center rounded-md border border-sky-300/20 bg-sky-500/[0.08] px-2 py-1 text-[10px] font-mono text-sky-200">
                    processing...
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Inline styles for custom scroll chrome without touching Tailwind config */}
      <style dangerouslySetInnerHTML={{__html: `
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.18); border-radius: 999px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,0.28); }
      `}} />
    </div>
  );
};

export default LangGraphPanel;
