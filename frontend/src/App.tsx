import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Threads from './pages/Threads.tsx';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100">
        <nav className="bg-white shadow-sm mb-4">
          <div className="container mx-auto px-4 py-3">
            <Link to="/" className="text-xl font-semibold text-blue-600 hover:text-blue-800">
              Agent Threads
            </Link>
          </div>
        </nav>

        <Routes>
          <Route path="/" element={<Threads />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App; 