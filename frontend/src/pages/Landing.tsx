import { useNavigate } from "react-router-dom";
import { Film } from "lucide-react";

const Landing = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-950 to-gray-900 text-gray-200">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <h1 className="text-5xl md:text-6xl font-bold mb-4 bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
            Hybrid RAG Analysis
          </h1>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto">
            Explore a movie recommendation system demonstrating a RAG (Retrieval-Augmented Generation) approach with LLMs.
          </p>
        </div>

        {/* Movies Use Case */}
        <div className="max-w-3xl mx-auto">
          <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg p-8 border border-gray-700 hover:border-purple-500 transition-all duration-300 hover:shadow-lg hover:shadow-purple-500/20">
            <div className="flex items-center justify-center w-16 h-16 bg-purple-500/20 rounded-lg mb-6">
              <Film className="w-8 h-8 text-purple-400" />
            </div>
            <h2 className="text-2xl font-bold mb-4 text-purple-400">
              LangGraph + Semantic Embeddings
            </h2>
            <p className="text-gray-300 mb-6 leading-relaxed">
              Movie recommendation system powered by semantic search. Ask for movie recommendations, and the system will use cosine distance in a vector database to find relevant matches. If your question is unrelated to movies, it will politely decline to answer.
            </p>
            <ul className="text-sm text-gray-400 mb-6 space-y-2">
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Semantic search with cosine distance</span>
              </li>
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Vector database integration</span>
              </li>
              <li className="flex items-start">
                <span className="text-purple-400 mr-2">•</span>
                <span>Context-aware routing with LangGraph</span>
              </li>
            </ul>
            <button
              onClick={() => navigate("/chat/movies")}
              className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors duration-200"
            >
              Try Movie Recommendations
            </button>
          </div>
        </div>

        {/* Footer Note */}
        <div className="mt-16 text-center text-gray-500 text-sm">
          <p>Each use case demonstrates different patterns and approaches to building RAG systems</p>
        </div>
      </div>
    </div>
  );
};

export default Landing;
