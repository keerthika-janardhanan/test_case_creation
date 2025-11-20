import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Sparkles } from 'lucide-react';

export function TestCasesPage() {
  return (
    <SidebarLayout>
      <div className="max-w-7xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Test Cases</h1>
          <p className="text-muted-foreground mt-2">
            AI-powered test case generation and management
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" />
              Test Case Generator
            </CardTitle>
            <CardDescription>
              Generate comprehensive test cases using AI
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-center py-12 text-muted-foreground">
              <p>Test Cases page - Coming soon with shadcn/ui</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </SidebarLayout>
  );
}
