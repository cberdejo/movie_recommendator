import { BrowserRouter, Routes, Route, Outlet, Navigate } from "react-router-dom";
import ChatPage from "./pages/Chat";
import WebSocketProvider from "./providers/WebSocketProvider";

const ChatLayout = () => (
  <WebSocketProvider>
    <Outlet />
  </WebSocketProvider>
);

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/chat/movies" replace />} />
        <Route element={<ChatLayout />}>
          <Route path="/chat/movies" element={<ChatPage useCase="movies" />} />
          <Route path="/chat/movies/:id" element={<ChatPage useCase="movies" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
