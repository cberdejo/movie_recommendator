import { useMemo } from "react";
import {
  MessageSquare,
  GitBranch,
  Search,
  Sparkles,
  MessageCircle,
  Play,
  CheckCircle2,
  X,
} from "lucide-react";
import type {
  GraphState,
  GraphNodeStatus,
} from "../../providers/WebSocketProvider";

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

const NODE_DEFS: NodeDef[] = [
  {
    id: "contextualize",
    label: "Contextualize",
    icon: MessageSquare,
    description: "Reformulates the question using history",
  },
  {
    id: "router",
    label: "Router",
    icon: GitBranch,
    description: "Classifies intent: retrieve or general",
  },
  {
    id: "retrieve",
    label: "Retrieve",
    icon: Search,
    description: "Semantic search in vector DB",
  },
  {
    id: "generate",
    label: "Generate",
    icon: Sparkles,
    description: "Generates response with context",
  },
  {
    id: "generate_general",
    label: "General Answer",
    icon: MessageCircle,
    description: "Generates general response",
  },
];

const statusColors: Record<GraphNodeStatus, string> = {
  idle: "border-gray-700 bg-gray-900/50",
  active: "border-purple-500 bg-purple-950/40 shadow-[0_0_20px_rgba(168,85,247,0.15)]",
  completed: "border-emerald-500/60 bg-emerald-950/20",
  error: "border-red-500/60 bg-red-950/20",
};

const dotColors: Record<GraphNodeStatus, string> = {
  idle: "bg-gray-600",
  active: "bg-purple-400",
  completed: "bg-emerald-400",
  error: "bg-red-400",
};

const iconColors: Record<GraphNodeStatus, string> = {
  idle: "text-gray-500",
  active: "text-purple-400",
  completed: "text-emerald-400",
  error: "text-red-400",
};

function NodeCard({ def, status, output, isInPath }: {
  def: NodeDef;
  status: GraphNodeStatus;
  output?: Record<string, any>;
  isInPath: boolean;
}) {
  const Icon = def.icon;
  const dimmed = !isInPath && status === "idle";

  return (
    <div
      className={`
        relative rounded-lg border px-3 py-2.5 transition-all duration-500
        ${statusColors[status]}
        ${dimmed ? "opacity-40" : "opacity-100"}
      `}
    >
      <div className="flex items-center gap-2.5">
        <div className={`relative flex-shrink-0 ${iconColors[status]}`}>
          <Icon className="w-4 h-4" />
          {status === "active" && (
            <span className="absolute -inset-1 rounded-full bg-purple-500/20 animate-ping" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-200 truncate">
              {def.label}
            </span>
            <span
              className={`
                w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors duration-500
                ${dotColors[status]}
                ${status === "active" ? "animate-pulse" : ""}
              `}
            />
          </div>
          <p className="text-[11px] text-gray-500 leading-tight mt-0.5">
            {def.description}
          </p>
        </div>
      </div>

      {output && Object.keys(output).length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-800/60">
          {output.reformulated_question && (
            <div className="mb-1">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">
                Reformulated
              </span>
              <p className="text-xs text-gray-300 mt-0.5 leading-relaxed line-clamp-2">
                "{output.reformulated_question}"
              </p>
            </div>
          )}
          {output.decision && (
            <div className="mb-1">
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">
                Decision
              </span>
              <span
                className={`ml-2 text-xs font-mono font-semibold ${output.decision === "RETRIEVE"
                  ? "text-blue-400"
                  : "text-amber-400"
                  }`}
              >
                {output.decision}
              </span>
            </div>
          )}
          {output.documents_count !== undefined && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-gray-500 font-medium">
                Documents
              </span>
              <span className="ml-2 text-xs font-mono text-blue-300">
                {output.documents_count} found
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EdgeLine({ active, completed }: { active: boolean; completed: boolean }) {
  return (
    <div className="flex justify-center -my-px">
      <div className="relative w-px h-5 min-h-[20px]">
        <div
          className={`
            absolute inset-0 w-px transition-colors duration-500
            ${completed ? "bg-emerald-500/40" : active ? "bg-purple-500/60" : "bg-gray-700/50"}
          `}
        />
        {active && (
          <div className="absolute inset-0 w-px bg-purple-400/80 animate-pulse" />
        )}
      </div>
    </div>
  );
}

function BranchSplit({
  leftActive,
  rightActive,
  leftCompleted,
  rightCompleted,
  decision,
}: {
  leftActive: boolean;
  rightActive: boolean;
  leftCompleted: boolean;
  rightCompleted: boolean;
  decision: string | null;
}) {
  const leftColor = leftCompleted
    ? "stroke-emerald-500/40"
    : leftActive
      ? "stroke-purple-500/60"
      : "stroke-gray-700/50";
  const rightColor = rightCompleted
    ? "stroke-emerald-500/40"
    : rightActive
      ? "stroke-purple-500/60"
      : "stroke-gray-700/50";

  return (
    <div className="relative -my-px">
      <svg
        viewBox="0 0 200 30"
        className="w-full h-6 block"
        preserveAspectRatio="none"
      >
        {/* Left branch: from center top (100,0) to left bottom (50,30) */}
        <path
          d="M 100 0 Q 100 15, 50 30"
          fill="none"
          className={`${leftColor} transition-all duration-500`}
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
        {/* Right branch: from center top (100,0) to right bottom (150,30) */}
        <path
          d="M 100 0 Q 100 15, 150 30"
          fill="none"
          className={`${rightColor} transition-all duration-500`}
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      {decision && (
        <>
          <span className="absolute left-1 bottom-0 text-[9px] font-mono text-blue-400/60">
            RETRIEVE
          </span>
          <span className="absolute right-1 bottom-0 text-[9px] font-mono text-amber-400/60">
            GENERAL
          </span>
        </>
      )}
    </div>
  );
}

function BranchMerge({
  leftCompleted,
  rightCompleted,
}: {
  leftCompleted: boolean;
  rightCompleted: boolean;
}) {
  const leftColor = leftCompleted
    ? "stroke-emerald-500/40"
    : "stroke-gray-700/50";
  const rightColor = rightCompleted
    ? "stroke-emerald-500/40"
    : "stroke-gray-700/50";

  return (
    <div className="-my-px">
      <svg
        viewBox="0 0 200 30"
        className="w-full h-6 block"
        preserveAspectRatio="none"
      >
        {/* From left top (50,0) and right top (150,0) to center bottom (100,30) */}
        <path
          d="M 50 0 Q 50 15, 100 30"
          fill="none"
          className={`${leftColor} transition-all duration-500`}
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
        <path
          d="M 150 0 Q 150 15, 100 30"
          fill="none"
          className={`${rightColor} transition-all duration-500`}
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}

const LangGraphPanel = ({ graphState, onClose }: LangGraphPanelProps) => {
  const { nodes, executionPath, isRunning } = graphState;

  const decision = nodes.router?.output?.decision ?? null;
  const pathSet = useMemo(() => new Set(executionPath), [executionPath]);

  const retrieveActive =
    nodes.retrieve?.status === "active" || nodes.generate?.status === "active";
  const generalActive = nodes.generate_general?.status === "active";
  const retrieveCompleted =
    nodes.generate?.status === "completed";
  const generalCompleted = nodes.generate_general?.status === "completed";

  const leftBranchInPath =
    pathSet.has("retrieve") || pathSet.has("generate");
  const rightBranchInPath = pathSet.has("generate_general");

  return (
    <div className="h-full flex flex-col bg-gray-950 border-l border-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="relative">
            <div
              className={`w-2 h-2 rounded-full ${isRunning ? "bg-purple-400 animate-pulse" : "bg-gray-600"
                }`}
            />
          </div>
          <h3 className="text-sm font-semibold text-gray-200">
            LangGraph Flow
          </h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
          aria-label="Close graph panel"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Graph */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="max-w-[280px] mx-auto space-y-0">
          {/* START node */}
          <div className="flex justify-center">
            <div
              className={`
                flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all duration-500
                ${isRunning || executionPath.length > 0
                  ? "border-emerald-500/50 text-emerald-400 bg-emerald-950/20"
                  : "border-gray-700 text-gray-500 bg-gray-900/50"
                }
              `}
            >
              <Play className="w-3 h-3" />
              Start
            </div>
          </div>

          <EdgeLine
            active={nodes.contextualize?.status === "active"}
            completed={nodes.contextualize?.status === "completed" || pathSet.has("contextualize")}
          />

          {/* Contextualize */}
          <NodeCard
            def={NODE_DEFS[0]}
            status={nodes.contextualize?.status ?? "idle"}
            output={nodes.contextualize?.output}
            isInPath={pathSet.has("contextualize") || isRunning}
          />

          <EdgeLine
            active={nodes.router?.status === "active"}
            completed={nodes.router?.status === "completed" || pathSet.has("router")}
          />

          {/* Router */}
          <NodeCard
            def={NODE_DEFS[1]}
            status={nodes.router?.status ?? "idle"}
            output={nodes.router?.output}
            isInPath={pathSet.has("router") || isRunning}
          />

          {/* Branch split */}
          <BranchSplit
            leftActive={retrieveActive}
            rightActive={generalActive}
            leftCompleted={leftBranchInPath}
            rightCompleted={rightBranchInPath}
            decision={decision}
          />

          {/* Two branches side by side */}
          <div className="grid grid-cols-2 gap-0">
            {/* Left: Retrieve path */}
            <div className="space-y-0 px-1">
              <NodeCard
                def={NODE_DEFS[2]}
                status={nodes.retrieve?.status ?? "idle"}
                output={nodes.retrieve?.output}
                isInPath={leftBranchInPath}
              />
              <EdgeLine
                active={nodes.generate?.status === "active"}
                completed={nodes.generate?.status === "completed"}
              />
              <NodeCard
                def={NODE_DEFS[3]}
                status={nodes.generate?.status ?? "idle"}
                output={nodes.generate?.output}
                isInPath={pathSet.has("generate")}
              />
            </div>

            {/* Right: General path */}
            <div className="flex flex-col h-full px-1">
              <NodeCard
                def={NODE_DEFS[4]}
                status={nodes.generate_general?.status ?? "idle"}
                output={nodes.generate_general?.output}
                isInPath={rightBranchInPath}
              />
              <div className="flex-1 flex justify-center relative -my-px">
                <div
                  className={`
                    w-px h-full transition-colors duration-500
                    ${generalCompleted ? "bg-emerald-500/40" : generalActive ? "bg-purple-500/60" : "bg-gray-700/50"}
                  `}
                />
                {generalActive && (
                  <div className="absolute top-0 bottom-0 w-px bg-purple-400/80 animate-pulse" />
                )}
              </div>
            </div>
          </div>

          {/* Branch merge */}
          <BranchMerge
            leftCompleted={retrieveCompleted}
            rightCompleted={generalCompleted}
          />

          {/* END node */}
          <div className="flex justify-center">
            <div
              className={`
                flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border transition-all duration-500
                ${retrieveCompleted || generalCompleted
                  ? "border-emerald-500/50 text-emerald-400 bg-emerald-950/20"
                  : "border-gray-700 text-gray-500 bg-gray-900/50"
                }
              `}
            >
              <CheckCircle2 className="w-3 h-3" />
              End
            </div>
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
  );
};

export default LangGraphPanel;
