import { ReactNode, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Home,
  VideoIcon,
  FileText,
  PlayCircle,
  Settings,
  Database,
  Search,
  LogOut,
  Menu,
  X,
  Sparkles,
  GitBranch,
  Ticket,
  Globe
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';

interface SidebarLayoutProps {
  children: ReactNode;
}

const navigation = [
  { name: 'Home', href: '/home', icon: Home },
  { name: 'Recorder', href: '/recorder', icon: VideoIcon },
  { name: 'Manual Tests', href: '/manual-tests', icon: FileText },
  { name: 'Test Cases', href: '/test-cases', icon: Sparkles },
  { name: 'Agentic', href: '/agentic', icon: PlayCircle },
  { name: 'Trial Runs', href: '/trial-runs', icon: PlayCircle },
  { name: 'Vector Search', href: '/vector-search', icon: Search },
  { name: 'Vector Manage', href: '/vector-manage', icon: Database },
  { name: 'GitOps', href: '/gitops', icon: GitBranch },
  { name: 'Jira', href: '/jira', icon: Ticket },
  { name: 'Website', href: '/website', icon: Globe },
  { name: 'Documents', href: '/documents', icon: FileText },
];

export function SidebarLayout({ children }: SidebarLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const { logout, userName } = useAuth();

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile sidebar */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="fixed inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <aside className="fixed inset-y-0 left-0 z-50 w-64 bg-card border-r border-border overflow-y-auto">
            <SidebarContent
              navigation={navigation}
              location={location}
              userName={userName}
              onLogout={logout}
              onClose={() => setSidebarOpen(false)}
            />
          </aside>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex grow flex-col gap-y-5 overflow-y-auto border-r border-border bg-card px-6">
          <SidebarContent
            navigation={navigation}
            location={location}
            userName={userName}
            onLogout={logout}
          />
        </div>
      </aside>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Mobile header */}
        <div className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-x-4 border-b border-border bg-card px-4 shadow-sm lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </Button>
          <div className="flex-1 text-sm font-semibold leading-6">
            Test Automation Studio
          </div>
        </div>

        <main className="py-6 px-4 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}

interface SidebarContentProps {
  navigation: typeof navigation;
  location: ReturnType<typeof useLocation>;
  userName?: string;
  onLogout: () => void;
  onClose?: () => void;
}

function SidebarContent({ navigation, location, userName, onLogout, onClose }: SidebarContentProps) {
  return (
    <>
      {/* Logo */}
      <div className="flex h-16 shrink-0 items-center gap-3">
        <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
          <Sparkles className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold">Test Automation</h1>
          <p className="text-xs text-muted-foreground">Studio</p>
        </div>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto lg:hidden"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex flex-1 flex-col gap-y-7">
        <ul role="list" className="flex flex-1 flex-col gap-y-1">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <li key={item.name}>
                <Link
                  to={item.href}
                  onClick={onClose}
                  className={cn(
                    'group flex gap-x-3 rounded-md p-2 text-sm leading-6 font-semibold transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                  )}
                >
                  <item.icon className="h-5 w-5 shrink-0" />
                  {item.name}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* User info and logout */}
        <div className="border-t border-border pt-4 pb-4">
          {userName && (
            <div className="mb-3 px-2">
              <p className="text-xs text-muted-foreground">Signed in as</p>
              <p className="text-sm font-medium truncate">{userName}</p>
            </div>
          )}
          <Button
            variant="ghost"
            className="w-full justify-start"
            onClick={onLogout}
          >
            <LogOut className="mr-2 h-4 w-4" />
            Logout
          </Button>
        </div>
      </nav>
    </>
  );
}
