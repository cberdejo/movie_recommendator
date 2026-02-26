import { useState, useEffect } from "react";
import Sidebar from "../components/chat/Sidebar.tsx";
import ChatView from "../components/chat/ChatView.tsx";
import { useParams } from "react-router-dom";
import type { UseCase } from "../lib/config";

interface ChatPageProps {
  useCase?: UseCase;
}

const ChatPage = ({ useCase = "movies" }: ChatPageProps) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(() => {
    // Check screen width and localStorage on initial render
    const savedState = localStorage.getItem('sidebarOpen');
    
    // On mobile (less than 768px width), default to closed regardless of saved state
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      return false;
    }
    
    // On desktop, use the saved state or default to true
    return savedState !== null ? savedState === 'true' : true;
  });
  
  const { id: idParam } = useParams();
  const conversationId =
    idParam && !Number.isNaN(Number(idParam)) ? Number(idParam) : undefined;

  // Save sidebar state to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('sidebarOpen', isSidebarOpen.toString());
  }, [isSidebarOpen]);

  // Handle window resize to close sidebar on mobile
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768 && isSidebarOpen) {
        setIsSidebarOpen(false);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isSidebarOpen]);

  return (
    <div className="flex h-screen bg-gray-950 text-gray-200">
      {/* Sidebar */}
      <Sidebar
        useCase={useCase}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Main Content */}
      <div className="flex-1 relative">
        <ChatView
          id={conversationId}
          useCase={useCase}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen((prev) => !prev)}
        />
      </div>
    </div>
  );
};

export default ChatPage;
