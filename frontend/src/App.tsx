import { BrowserRouter, Routes, Route } from "react-router-dom";
import ChatPage from "./pages/Chat";
import Landing from "./pages/Landing";
import WebSocketProvider from "./providers/WebSocketProvider";
import type { ReactNode } from "react";

const ChatWrapper = ({ children }: { children: ReactNode }) => (
  <WebSocketProvider>{children}</WebSocketProvider>
);

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/chat/movies"
          element={
            <ChatWrapper>
              <ChatPage useCase="movies" />
            </ChatWrapper>
          }
        />
        <Route
          path="/chat/movies/:id"
          element={
            <ChatWrapper>
              <ChatPage useCase="movies" />
            </ChatWrapper>
          }
        />

       
      </Routes>
    </BrowserRouter>
  );
};

export default App;
