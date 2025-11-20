import React from 'react';

interface SimpleLayoutProps {
  children: React.ReactNode;
}

export function SimpleLayout({ children }: SimpleLayoutProps) {
  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      fontFamily: 'sans-serif'
    }}>
      <div style={{
        padding: '20px',
        color: 'white'
      }}>
        <h1>Simple Layout Working</h1>
        <div>{children}</div>
      </div>
    </div>
  );
}