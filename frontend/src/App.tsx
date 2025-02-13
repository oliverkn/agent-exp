import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Agents from './pages/Agents.tsx';

function App() {
  return (
    <Router>
      <div className="bg-gray-100">
        <Routes>
          <Route path="/" element={<Agents />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App; 