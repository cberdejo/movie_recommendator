import { useState, useEffect, useCallback, useRef } from "react";
import Sidebar from "../components/chat/Sidebar.tsx";
import ChatView from "../components/chat/ChatView.tsx";
import LangGraphPanel from "../components/chat/LangGraphPanel.tsx";
import { useParams } from "react-router-dom";
import { useWebSocket } from "../providers/WebSocketProvider.tsx";
import { PanelLeft, PanelRight } from "lucide-react";
import type { UseCase } from "../lib/config";

interface ChatPageProps {
  useCase?: UseCase;
}

const MIN_SIDEBAR = 220;
const MAX_SIDEBAR = 480;
const MIN_GRAPH = 260;
const MAX_GRAPH = 600;
const DEFAULT_SIDEBAR = 320;
const DEFAULT_GRAPH = 360;

const ChatPage = ({ useCase = "movies" }: ChatPageProps) => {
  const { graphState } = useWebSocket();

  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    const saved = localStorage.getItem("sidebarOpen");
    if (typeof window !== "undefined" && window.innerWidth < 768) return false;
    return saved !== null ? saved === "true" : true;
  });

  const [isGraphOpen, setIsGraphOpen] = useState(() => {
    const saved = localStorage.getItem("graphPanelOpen");
    if (typeof window !== "undefined" && window.innerWidth < 768) return false;
    return saved !== null ? saved === "true" : true;
  });

  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem("sidebarWidth");
    return saved ? Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, Number(saved))) : DEFAULT_SIDEBAR;
  });

  const [graphWidth, setGraphWidth] = useState(() => {
    const saved = localStorage.getItem("graphWidth");
    return saved ? Math.max(MIN_GRAPH, Math.min(MAX_GRAPH, Number(saved))) : DEFAULT_GRAPH;
  });

  const draggingRef = useRef<"sidebar" | "graph" | null>(null);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  const { id: idParam } = useParams();
  const conversationId =
    idParam && !Number.isNaN(Number(idParam)) ? Number(idParam) : undefined;

  useEffect(() => {
    localStorage.setItem("sidebarOpen", isSidebarOpen.toString());
  }, [isSidebarOpen]);

  useEffect(() => {
    localStorage.setItem("graphPanelOpen", isGraphOpen.toString());
  }, [isGraphOpen]);

  useEffect(() => {
    localStorage.setItem("sidebarWidth", sidebarWidth.toString());
  }, [sidebarWidth]);

  useEffect(() => {
    localStorage.setItem("graphWidth", graphWidth.toString());
  }, [graphWidth]);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setIsSidebarOpen(false);
        setIsGraphOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const onMouseDown = useCallback(
    (panel: "sidebar" | "graph", e: React.MouseEvent) => {
      e.preventDefault();
      draggingRef.current = panel;
      startXRef.current = e.clientX;
      startWidthRef.current = panel === "sidebar" ? sidebarWidth : graphWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [sidebarWidth, graphWidth],
  );

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const delta = e.clientX - startXRef.current;

      if (draggingRef.current === "sidebar") {
        const newW = Math.max(MIN_SIDEBAR, Math.min(MAX_SIDEBAR, startWidthRef.current + delta));
        setSidebarWidth(newW);
      } else {
        const newW = Math.max(MIN_GRAPH, Math.min(MAX_GRAPH, startWidthRef.current - delta));
        setGraphWidth(newW);
      }
    };

    const onMouseUp = () => {
      if (draggingRef.current) {
        draggingRef.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return (
    <div className="flex h-screen bg-gray-950 text-gray-200 overflow-hidden">
      {/* Left Sidebar */}
      {isSidebarOpen && (
        <>
          <div style={{ width: sidebarWidth, minWidth: sidebarWidth }} className="hidden md:block">
            <Sidebar
              useCase={useCase}
              isOpen={isSidebarOpen}
              onClose={() => setIsSidebarOpen(false)}
            />
          </div>
          {/* Sidebar resize handle */}
          <div
            className="hidden md:flex w-1 cursor-col-resize items-center justify-center group hover:bg-purple-500/20 transition-colors"
            onMouseDown={(e) => onMouseDown("sidebar", e)}
          >
            <div className="w-px h-8 bg-gray-700 group-hover:bg-purple-500 transition-colors rounded-full" />
          </div>
        </>
      )}

      {/* Mobile sidebar (overlay) */}
      <div className="md:hidden">
        <Sidebar
          useCase={useCase}
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
        />
      </div>

      {/* Center: Chat */}
      <div className="flex-1 min-w-0 relative flex flex-col">
        {/* Toggle buttons bar */}
        <div className="absolute top-3 left-2 z-10 flex gap-1">
          {!isSidebarOpen && (
            <button
              onClick={() => setIsSidebarOpen(true)}
              className="p-1.5 rounded-md bg-gray-900/80 border border-gray-800 hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors backdrop-blur-sm"
              aria-label="Open sidebar"
            >
              <PanelLeft className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="absolute top-3 right-24 z-10">
          {!isGraphOpen && (
            <button
              onClick={() => setIsGraphOpen(true)}
              className="p-1.5 rounded-md bg-gray-900/80 border border-gray-800 hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors backdrop-blur-sm"
              aria-label="Open graph panel"
            >
              <PanelRight className="w-4 h-4" />
            </button>
          )}
        </div>

        <ChatView
          id={conversationId}
          useCase={useCase}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        />
      </div>

      {/* Right: Graph Panel */}
      {isGraphOpen && (
        <>
          {/* Graph resize handle */}
          <div
            className="hidden md:flex w-1 cursor-col-resize items-center justify-center group hover:bg-purple-500/20 transition-colors"
            onMouseDown={(e) => onMouseDown("graph", e)}
          >
            <div className="w-px h-8 bg-gray-700 group-hover:bg-purple-500 transition-colors rounded-full" />
          </div>
          <div
            style={{ width: graphWidth, minWidth: graphWidth }}
            className="hidden md:block"
          >
            <LangGraphPanel
              graphState={graphState}
              onClose={() => setIsGraphOpen(false)}
            />
          </div>
        </>
      )}
    </div>
  );
};

export default ChatPage;
