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
    description: "Classifies query & media type",
  },
  contextualize: {
    id: "contextualize",
    label: "Contextualize",
    icon: ScanSearch,
    description: "Rewrites query from chat history",
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

// High-temperature visual theme: "Cyber-Glassmorphism"
const theme = {
  idle: {
    card: "border-white/5 bg-white/[0.02] hover:bg-white/[0.04]",
    icon: "text-slate-500 bg-white/5",
    text: "text-slate-400",
    dot: "bg-slate-700",
  },
  active: {
    card: "border-cyan-500/50 bg-cyan-950/20 shadow-[0_0_30px_-5px_rgba(6,182,212,0.3)] ring-1 ring-cyan-500/20",
    icon: "text-cyan-300 bg-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.5)]",
    text: "text-cyan-100",
    dot: "bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.8)]",
  },
  completed: {
    card: "border-indigo-500/20 bg-indigo-950/10",
    icon: "text-indigo-400 bg-indigo-500/10",
    text: "text-indigo-200",
    dot: "bg-indigo-500",
  },
  error: {
    card: "border-rose-500/40 bg-rose-950/20",
    icon: "text-rose-400 bg-rose-500/10",
    text: "text-rose-200",
    dot: "bg-rose-500",
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
      relative rounded-xl border px-3.5 py-3 transition-all duration-700 backdrop-blur-md overflow-hidden
      ${currentTheme.card}
      ${dimmed ? "opacity-30 scale-[0.98] grayscale-[0.5]" : "opacity-100 scale-100"}
    `}>
      {/* Active scanning beam effect */}
      {status === "active" && (
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-cyan-400/5 to-transparent h-[200%] animate-[scan_2s_linear_infinite]" />
      )}

      <div className="relative flex items-start gap-3">
        <div className={`relative flex-shrink-0 p-2 rounded-lg transition-colors duration-500 ${currentTheme.icon}`}>
          <Icon className="w-4 h-4" />
          {status === "active" && (
            <span className="absolute inset-0 rounded-lg ring-1 ring-cyan-400/50 animate-ping opacity-50" />
          )}
        </div>
        
        <div className="flex-1 min-w-0 pt-0.5">
          <div className="flex items-center justify-between gap-2">
            <span className={`text-[13px] font-semibold tracking-wide truncate ${currentTheme.text}`}>
              {def.label}
            </span>
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-all duration-500
              ${currentTheme.dot} ${status === "active" ? "animate-pulse" : ""}`}
            />
          </div>
          <p className="text-[10px] text-slate-500 leading-tight mt-1 font-medium tracking-wide uppercase">
            {def.description}
          </p>
        </div>
      </div>

      {output && Object.keys(output).length > 0 && (
        <div className="relative mt-3 pt-3 border-t border-white/5 grid grid-cols-2 gap-2">
          {output.decision && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Route</span>
              <span className={`text-[11px] font-mono font-bold rounded px-1.5 py-0.5 w-max
                ${output.decision === "RETRIEVE" ? "bg-indigo-500/10 text-indigo-300 border border-indigo-500/20" : 
                  "bg-amber-500/10 text-amber-300 border border-amber-500/20"}`}>
                {output.decision}
              </span>
            </div>
          )}
          {output.media_type && output.media_type !== "any" && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Media</span>
              <span className="text-[11px] font-mono text-fuchsia-300 bg-fuchsia-500/10 border border-fuchsia-500/20 rounded px-1.5 py-0.5 w-max">
                {output.media_type}
              </span>
            </div>
          )}
          {output.rewritten_question && (
            <div className="flex flex-col gap-0.5 col-span-2">
              <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Rewrite</span>
              <span className="text-[11px] text-emerald-200 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-1 leading-snug break-words">
                {output.rewritten_question}
              </span>
            </div>
          )}
          {output.rewrote === false && (
            <div className="flex flex-col gap-0.5">
              <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Status</span>
              <span className="text-[11px] font-mono text-slate-300 bg-white/5 border border-white/10 rounded px-1.5 py-0.5 w-max">
                unchanged
              </span>
            </div>
          )}
          {output.documents_count !== undefined && (
            <div className="flex flex-col gap-0.5 col-span-2">
              <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Vectors</span>
              <div className="flex items-center gap-1.5 text-[11px] font-mono text-cyan-300 bg-cyan-500/10 border border-cyan-500/20 rounded px-1.5 py-0.5 w-max">
                <Activity className="w-3 h-3" />
                {output.documents_count} hits found
              </div>
            </div>
          )}
          {output.needs_reask && (
            <div className="col-span-2 mt-1">
              <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300 text-[10px] uppercase font-bold tracking-wider">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-rose-500"></span>
                </span>
                Sub-optimal Match: Re-asking
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Advanced SVG Edge Helpers with Glow Filters
// ---------------------------------------------------------------------------

const getEdgeStyle = (active: boolean, completed: boolean) => {
  if (active) return "stroke-cyan-400 drop-shadow-[0_0_5px_rgba(6,182,212,0.8)]";
  if (completed) return "stroke-indigo-500/50";
  return "stroke-white/10";
};

function EdgeLine({ active, completed }: { active: boolean; completed: boolean }) {
  return (
    <div className="flex justify-center -my-px relative z-0">
      <div className="relative w-0.5 h-6">
        <div className={`absolute inset-0 transition-all duration-700
          ${completed ? "bg-indigo-500/40" : active ? "bg-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.8)]" : "bg-white/10"}`}
        />
        {active && <div className="absolute inset-0 bg-cyan-300 blur-[2px] animate-pulse" />}
      </div>
    </div>
  );
}

function RouterSplit({ decision, pathSet }: { decision: string | null; pathSet: Set<string>; }) {
  const leftActive  = pathSet.has("contextualize") || pathSet.has("retrieve") || pathSet.has("generate_retrieve") || pathSet.has("reask_user");
  const rightActive = pathSet.has("generate_general");

  return (
    <div className="relative -my-px z-0">
      <svg viewBox="0 0 200 36" className="w-full h-8 block" preserveAspectRatio="none">
        <path d="M 100 0 Q 100 18, 45 36" fill="none"
          className={`${getEdgeStyle(decision === "RETRIEVE" && !leftActive, leftActive)} transition-all duration-700`}
          strokeWidth={leftActive ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
        <path d="M 100 0 Q 100 18, 155 36" fill="none"
          className={`${getEdgeStyle(decision === "GENERAL" && !rightActive, rightActive)} transition-all duration-700`}
          strokeWidth={rightActive ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function RetrieveSplit({ pathSet }: { pathSet: Set<string> }) {
  const leftActive  = pathSet.has("generate_retrieve");
  const rightActive = pathSet.has("reask_user");

  return (
    <div className="relative -my-px z-0">
      <svg viewBox="0 0 160 30" className="w-full h-7 block" preserveAspectRatio="none">
        <path d="M 80 0 Q 80 15, 35 30" fill="none"
          className={`${getEdgeStyle(false, leftActive)} transition-all duration-700`}
          strokeWidth={leftActive ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
        <path d="M 80 0 Q 80 15, 125 30" fill="none"
          className={`${getEdgeStyle(false, rightActive)} transition-all duration-700`}
          strokeWidth={rightActive ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  );
}

function FinalMerge({ pathSet }: { pathSet: Set<string> }) {
  const a = pathSet.has("generate_retrieve");
  const b = pathSet.has("reask_user");
  const c = pathSet.has("generate_general");

  return (
    <div className="-my-px z-0 relative">
      <svg viewBox="0 0 200 36" className="w-full h-8 block" preserveAspectRatio="none">
        <path d="M 35  0 Q 35  18, 100 36" fill="none"
          className={`${getEdgeStyle(false, a)} transition-all duration-700`}
          strokeWidth={a ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
        <path d="M 80  0 Q 80  18, 100 36" fill="none"
          className={`${getEdgeStyle(false, b)} transition-all duration-700`}
          strokeWidth={b ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
        <path d="M 155 0 Q 155 18, 100 36" fill="none"
          className={`${getEdgeStyle(false, c)} transition-all duration-700`}
          strokeWidth={c ? "2" : "1.5"} vectorEffect="non-scaling-stroke" />
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

  const isRetrievePath   = pathSet.has("contextualize") || pathSet.has("retrieve") || pathSet.has("generate_retrieve") || pathSet.has("reask_user");
  const isGeneralPath    = pathSet.has("generate_general");
  const anyTerminalDone  = pathSet.has("generate_retrieve") || pathSet.has("reask_user") || pathSet.has("generate_general");

  return (
    <div className="h-full flex flex-col bg-[#030305] text-white border-l border-white/10 relative overflow-hidden font-sans">
      
      {/* Cinematic Background FX */}
      <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-cyan-500/10 rounded-full blur-[120px] -translate-x-1/2 -translate-y-1/2 pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-indigo-600/10 rounded-full blur-[150px] translate-x-1/3 translate-y-1/3 pointer-events-none" />
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGNpcmNsZSBjeD0iMSIgY3k9IjEiIHI9IjEiIGZpbGw9InJnYmEoMjU1LDI1NSwyNTUsMC4wMykiLz48L3N2Zz4=')] [mask-image:linear-gradient(to_bottom,white,transparent)] pointer-events-none" />

      {/* Header */}
      <div className="relative z-10 flex items-center justify-between px-5 py-4 border-b border-white/5 backdrop-blur-xl bg-black/20">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className={`w-2.5 h-2.5 rounded-full transition-colors duration-500 relative z-10
              ${isRunning ? "bg-cyan-400" : "bg-slate-600"}`} />
            {isRunning && (
              <div className="absolute inset-0 bg-cyan-400 rounded-full blur-sm animate-pulse" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-bold tracking-wide text-white drop-shadow-md">Nexus Graph</h3>
            <p className="text-[10px] uppercase tracking-widest text-cyan-400/70 font-semibold mt-0.5">Live Execution State</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all backdrop-blur-md border border-white/5"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-8 relative z-10 custom-scrollbar">
        <div className="max-w-[340px] mx-auto">

          {/* START */}
          <div className="flex justify-center mb-0 relative z-10">
            <div className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-[11px] font-bold tracking-widest uppercase border transition-all duration-700 backdrop-blur-md
              ${isRunning || executionPath.length > 0
                ? "border-cyan-500/50 text-cyan-300 bg-cyan-950/30 shadow-[0_0_15px_rgba(6,182,212,0.2)]"
                : "border-white/10 text-slate-400 bg-white/5"}`}>
              <Play className="w-3.5 h-3.5" />
              Init
            </div>
          </div>

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
          <div className="grid grid-cols-[1fr_0.9fr] gap-3 relative z-10">
            {/* Left: retrieve path */}
            <div className="flex flex-col">
              <NodeCard
                def={NODE_DEFS.contextualize}
                status={nodeStatus("contextualize")}
                output={nodeOutput("contextualize")}
                isInPath={isRetrievePath}
              />
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
              <RetrieveSplit pathSet={pathSet} />
              
              <div className="grid grid-cols-2 gap-2">
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

            {/* Right: general path */}
            <div className="flex flex-col">
              <NodeCard
                def={NODE_DEFS.generate_general}
                status={nodeStatus("generate_general")}
                output={nodeOutput("generate_general")}
                isInPath={isGeneralPath}
              />
            </div>
          </div>

          <FinalMerge pathSet={pathSet} />

          {/* END */}
          <div className="flex justify-center mt-0 relative z-10">
            <div className={`flex items-center gap-2 px-4 py-1.5 rounded-full text-[11px] font-bold tracking-widest uppercase border transition-all duration-700 backdrop-blur-md
              ${anyTerminalDone
                ? "border-indigo-500/50 text-indigo-300 bg-indigo-950/30 shadow-[0_0_15px_rgba(99,102,241,0.2)]"
                : "border-white/10 text-slate-500 bg-white/5"}`}>
              <CheckCircle2 className="w-3.5 h-3.5" />
              Terminate
            </div>
          </div>

          {/* Holographic Execution Log */}
          {executionPath.length > 0 && (
            <div className="mt-10 p-4 rounded-xl border border-white/5 bg-white/[0.02] backdrop-blur-md">
              <div className="flex items-center gap-2 mb-3">
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                <h4 className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-bold">
                  Trace Log
                </h4>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {executionPath.map((node, i) => (
                  <div key={`${node}-${i}`} className="flex items-center gap-1.5">
                    <span className="inline-flex items-center px-2 py-1 rounded-md text-[10px] font-mono bg-black/40 border border-white/5 text-slate-300 shadow-inner">
                      <span className="text-cyan-500/50 mr-1.5">{i + 1}</span>
                      {node}
                    </span>
                    {i < executionPath.length - 1 && (
                      <span className="text-white/20 text-[10px]">→</span>
                    )}
                  </div>
                ))}
                {isRunning && (
                  <span className="inline-flex items-center px-2 py-1 rounded-md text-[10px] font-mono border border-cyan-500/30 text-cyan-400 bg-cyan-500/10 animate-pulse">
                    processing...
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
      
      {/* Inline styles for custom animations that are tricky in raw Tailwind without config */}
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes scan {
          0% { transform: translateY(-100%); }
          100% { transform: translateY(100%); }
        }
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(6,182,212,0.5); }
      `}} />
    </div>
  );
};

export default LangGraphPanel;