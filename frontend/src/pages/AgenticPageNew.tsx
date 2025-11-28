import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Zap } from 'lucide-react';

export function AgenticPage() {
  return (
    <SidebarLayout>
      <div className="max-w-7xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agentic Flow</h1>
          <p className="text-muted-foreground mt-2">
            AI-powered automated test script generation
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              AI Agent
            </CardTitle>
            <CardDescription>
              Generate test scripts automatically with AI agents
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-center py-12 text-muted-foreground">
              <p>Agentic Flow page - Coming soon with shadcn/ui</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </SidebarLayout>
  );
}
