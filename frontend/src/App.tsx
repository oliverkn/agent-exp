import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import Agents from './pages/Agents.tsx';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-100">
        <nav className="bg-white shadow-sm mb-4">
          <div className="container mx-auto px-4 py-3">
            <Link to="/" className="text-xl font-semibold text-blue-600 hover:text-blue-800">
              Agent Interface
            </Link>
          </div>
        </nav>

        <Routes>
          <Route path="/" element={<Agents />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App; 