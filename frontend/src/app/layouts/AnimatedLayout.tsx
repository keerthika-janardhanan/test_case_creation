import React from 'react';
import { useLocation, NavLink as RouterNavLink } from 'react-router-dom';
import { useState } from 'react';
import { ChevronDown, ChevronRight, Home, Database, TestTube, Cog, Search } from 'lucide-react';
import './AnimatedLayout.css';

interface NavLinkConfig {
  label: string;
  to: string;
  icon?: React.ComponentType<any>;
}

const NAV_LINKS: NavLinkConfig[] = [
  { label: "Home Dashboard", to: "/", icon: Home },
  { label: "Recorder & Ingest", to: "/recorder", icon: Database },
  { label: "Jira Ingestion", to: "/jira", icon: Database },
  { label: "Website Ingestion", to: "/website", icon: Database },
  { label: "Document Ingestion", to: "/documents", icon: Database },
  { label: "Generate Test Cases", to: "/test-cases", icon: TestTube },
  { label: "Test Script Generator", to: "/script-generator", icon: TestTube },
  { label: "Vector Manage", to: "/vector-manage", icon: Search },
  { label: "Settings", to: "/settings", icon: Cog },
];

interface AnimatedLayoutProps {
  children: React.ReactNode;
}

export function AnimatedLayout({ children }: AnimatedLayoutProps) {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  
  // Group the ingestion-related links under a dropdown titled "Vector Ingestion"
  const INGEST_PATHS = new Set(["/recorder", "/jira", "/website", "/documents"]);
  const ingestLinks = NAV_LINKS.filter((l) => INGEST_PATHS.has(l.to));
  const otherLinks = NAV_LINKS.filter((l) => !INGEST_PATHS.has(l.to));
  const isIngestActive = ingestLinks.some((link) => location.pathname.startsWith(link.to));
  const [ingestOpen, setIngestOpen] = useState(true);

  return (
    <div className="animated-layout">
      {/* Floating Background Shapes */}
      <div className="floating-shapes">
        <div className="shape shape-1"></div>
        <div className="shape shape-2"></div>
        <div className="shape shape-3"></div>
        <div className="shape shape-4"></div>
        <div className="shape shape-5"></div>
      </div>

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <h1 className="sidebar-title">Test Artifact Suite</h1>
          <button 
            className="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <ChevronRight className={`toggle-icon ${sidebarOpen ? 'rotated' : ''}`} />
          </button>
        </div>

        <nav className="sidebar-nav">
          {/* Vector Ingestion Dropdown */}
          <div className="nav-section">
            <button
              className={`nav-dropdown ${isIngestActive ? 'active' : ''}`}
              onClick={() => setIngestOpen(!ingestOpen)}
            >
              <div className="nav-dropdown-content">
                <Database className="nav-icon" />
                <span className="nav-label">Vector Ingestion</span>
              </div>
              {ingestOpen ? <ChevronDown className="dropdown-icon" /> : <ChevronRight className="dropdown-icon" />}
            </button>
            
            {ingestOpen && (
              <div className="nav-submenu">
                {ingestLinks.map((link) => {
                  const isActive = location.pathname.startsWith(link.to);
                  const IconComponent = link.icon;
                  return (
                    <RouterNavLink
                      key={link.to}
                      to={link.to}
                      className={`nav-link submenu ${isActive ? 'active' : ''}`}
                    >
                      {IconComponent && <IconComponent className="nav-icon" />}
                      <span className="nav-label">{link.label}</span>
                    </RouterNavLink>
                  );
                })}
              </div>
            )}
          </div>

          {/* Other Navigation Links */}
          <div className="nav-section">
            {otherLinks.map((link) => {
              const isActive = location.pathname === link.to || 
                (link.to !== '/' && location.pathname.startsWith(link.to));
              const IconComponent = link.icon;
              return (
                <RouterNavLink
                  key={link.to}
                  to={link.to}
                  className={`nav-link ${isActive ? 'active' : ''}`}
                >
                  {IconComponent && <IconComponent className="nav-icon" />}
                  <span className="nav-label">{link.label}</span>
                </RouterNavLink>
              );
            })}
          </div>
        </nav>
      </aside>

      {/* Main Content */}
      <main className={`main-content ${sidebarOpen ? 'with-sidebar' : 'full-width'}`}>
        <header className="main-header">
          <div className="header-content">
            <h2 className="page-title">Test Artifact Suite</h2>
            <div className="header-actions">
              <div className="status-indicator">
                <span className="status-dot"></span>
                <span>System Ready</span>
              </div>
            </div>
          </div>
        </header>

        <div className="content-area">
          {children}
        </div>
      </main>
    </div>
  );
}