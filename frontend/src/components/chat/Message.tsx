import { useState, useEffect, lazy, Suspense } from "react";
import { ChevronRight, Copy, Check } from "lucide-react";
import { MessageType } from "../../lib/types";
import remarkGfm from "remark-gfm";

// Lazy load ReactMarkdown for better initial load performance
const ReactMarkdown = lazy(() => import("react-markdown"));

// Import highlight.js (smaller alternative to react-syntax-highlighter)
import hljs from "highlight.js/lib/core";
// Only import the languages we need
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import python from "highlight.js/lib/languages/python";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import xml from "highlight.js/lib/languages/xml"; // For HTML
import markdown from "highlight.js/lib/languages/markdown";
import go from "highlight.js/lib/languages/go";
import csharp from "highlight.js/lib/languages/csharp";

// Register only the languages we need
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("json", json);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("html", xml); // HTML uses the XML highlighter
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("md", markdown);
hljs.registerLanguage("go", go);
hljs.registerLanguage("csharp", csharp);
hljs.registerLanguage("cs", csharp);

// Import only the styles we need (vs-dark theme is similar to vsc-dark-plus)
import "highlight.js/styles/atom-one-dark.css";

interface CodeProps {
  node?: any;
  inline?: boolean;
  className?: string;
  children?: React.ReactNode;
}

const CodeComponent = ({ inline, className, children }: CodeProps) => {
  const [copied, setCopied] = useState(false);
  const codeString = String(children).replace(/\n$/, "");
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  
  useEffect(() => {
    // Reset copied state after 2 seconds
    if (copied) {
      const timer = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [copied]);

  // Handle the copy action
  const handleCopy = () => {
    navigator.clipboard.writeText(codeString);
    setCopied(true);
  };

  if (inline) {
    return <code className={className}>{children}</code>;
  }

  // For code blocks, use highlight.js
  let highlightedCode = "";
  try {
    // Check if the language is registered
    if (language && hljs.getLanguage(language)) {
      highlightedCode = hljs.highlight(codeString, { language }).value;
    } else {
      // Fallback to bash for unknown languages
      highlightedCode = hljs.highlight(codeString, { language: 'bash' }).value;
    }
  } catch (error) {
    // If any error occurs, fallback to bash
    console.log(`Highlight.js error: ${error}`);
    highlightedCode = hljs.highlight(codeString, { language: 'bash' }).value;
  }

  return (
    <div className="relative group">
      <pre className="bg-gray-800 rounded p-3 overflow-x-auto">
        <code
          className={`language-${language}`}
          dangerouslySetInnerHTML={{ __html: highlightedCode }}
        />
      </pre>
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 p-1.5 bg-gray-700 hover:bg-gray-600 rounded text-gray-300 
                  opacity-0 group-hover:opacity-100 transition-opacity"
        aria-label="Copy code"
      >
        {copied ? <Check size={16} /> : <Copy size={16} />}
      </button>
    </div>
  );
};

const MessageComponent = ({ message }: { message: MessageType }) => {
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);
  const isAssistant = message.Role === "assistant";
  const hasThinking = isAssistant && message.Thinking;

  const markdownComponents = {
    code: CodeComponent,
  };

  return (
    <div className={`py-4 ${isAssistant ? "bg-gray-900/50" : ""}`}>
      <div className="max-w-4xl mx-auto px-4">
        <div className="mb-1 text-xs font-medium text-gray-500">
          {isAssistant ? "Assistant" : "You"}
        </div>

        {hasThinking && (
          <div className="mb-2">
            <button
              onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
              className="flex items-center gap-2 text-xs text-gray-600 hover:text-gray-500 transition-colors"
              aria-expanded={isThinkingExpanded}
            >
              <ChevronRight
                className={`w-3 h-3 transition-transform ${
                  isThinkingExpanded ? "rotate-90" : ""
                }`}
              />
              <span>
                Thought process
                {isThinkingExpanded &&
                  message.ThinkingTime &&
                  ` (${message.ThinkingTime.toFixed(2)}s)`}
              </span>
            </button>

            {isThinkingExpanded && message.Thinking && (
              <div className="mt-2 pl-6 py-2 border-l-2 border-purple-800/30 text-sm text-gray-400 bg-purple-900/10 rounded-r-md">
                <Suspense fallback={<div>Loading...</div>}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={markdownComponents}
                  >
                    {message.Thinking}
                  </ReactMarkdown>
                </Suspense>
              </div>
            )}
          </div>
        )}

        <div
          className={`${
            isAssistant
              ? "text-gray-300"
              : "text-gray-200 bg-gray-800/50 p-3 rounded-lg"
          }`}
        >
          <Suspense fallback={<div>Loading...</div>}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {message.Content}
            </ReactMarkdown>
          </Suspense>
        </div>
      </div>
    </div>
  );
};

export default MessageComponent;
