import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

// Import global styles first
import "./styles/global.css";

// Simple test component to debug
function TestPage() {
  return (
    <div style={{ 
      padding: '20px', 
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
      minHeight: '100vh',
      color: 'white',
      fontFamily: 'sans-serif'
    }}>
      <h1>Test Page Working!</h1>
      <p>If you can see this, the basic routing is working.</p>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<TestPage />} />
        <Route path="*" element={<TestPage />} />
      </Routes>
    </BrowserRouter>
  );
}