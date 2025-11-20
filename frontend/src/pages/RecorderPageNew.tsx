import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { VideoIcon, PlayCircle, StopCircle } from 'lucide-react';

export function RecorderPage() {
  return (
    <SidebarLayout>
      <div className="max-w-7xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Flow Recorder</h1>
          <p className="text-muted-foreground mt-2">
            Record user interactions and capture flow metadata
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <VideoIcon className="h-5 w-5" />
              Recording Controls
            </CardTitle>
            <CardDescription>
              Start recording user flows to capture interactions
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4">
              <Button size="lg">
                <PlayCircle className="mr-2 h-5 w-5" />
                Start Recording
              </Button>
              <Button size="lg" variant="outline">
                <StopCircle className="mr-2 h-5 w-5" />
                Stop Recording
              </Button>
            </div>
            <div className="text-sm text-muted-foreground">
              This is a placeholder. The full recorder functionality will be migrated from Chakra UI.
            </div>
          </CardContent>
        </Card>
      </div>
    </SidebarLayout>
  );
}
