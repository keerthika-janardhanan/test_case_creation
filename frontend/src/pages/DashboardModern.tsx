import { useState } from 'react';
import { VideoIcon, PlayIcon, Clock, Globe } from 'lucide-react';
import axios from 'axios';
import { toast, Toaster } from 'sonner';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';

const API_BASE = 'http://localhost:8000/api';

interface FormData {
  url: string;
  flowName: string;
  timer: number;
}

export default function DashboardModern() {
  const [isLoading, setIsLoading] = useState(false);
  const [formData, setFormData] = useState<FormData>({
    url: 'https://example.com',
    flowName: 'e.g., Login Flow',
    timer: 30
  });

  const handleStartRecording = async () => {
    if (!formData.url || !formData.flowName) {
      toast.error('Please fill in URL and Flow Name');
      return;
    }

    setIsLoading(true);
    try {
      const response = await axios.post(`${API_BASE}/start-recording`, {
        url: formData.url,
        flow_name: formData.flowName,
        timeout: formData.timer
      });
      toast.success('Recording started successfully!');
      console.log('Recording session:', response.data);
    } catch (error) {
      toast.error('Failed to start recording');
      console.error('Recording error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <SidebarLayout>
      <Toaster position="top-right" />
      
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-2">
            Start recording user flows and generate automated test cases
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Total Recordings
              </CardTitle>
              <VideoIcon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">12</div>
              <p className="text-xs text-muted-foreground">
                +2 from last week
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Test Cases
              </CardTitle>
              <PlayIcon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">48</div>
              <p className="text-xs text-muted-foreground">
                Generated this month
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Success Rate
              </CardTitle>
              <Badge variant="default" className="ml-auto">
                95%
              </Badge>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">46/48</div>
              <p className="text-xs text-muted-foreground">
                Passing tests
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                Active Sessions
              </CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">0</div>
              <p className="text-xs text-muted-foreground">
                Currently recording
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Recording Form */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <VideoIcon className="h-5 w-5" />
              Start New Recording
            </CardTitle>
            <CardDescription>
              Record a new user flow to generate test cases automatically
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="url" className="flex items-center gap-2">
                  <Globe className="h-4 w-4" />
                  Target URL
                </Label>
                <Input
                  id="url"
                  placeholder="https://example.com"
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="flowName">Flow Name</Label>
                <Input
                  id="flowName"
                  placeholder="e.g., Login Flow"
                  value={formData.flowName}
                  onChange={(e) => setFormData({ ...formData, flowName: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="timer" className="flex items-center gap-2">
                <Clock className="h-4 w-4" />
                Timeout (seconds)
              </Label>
              <Input
                id="timer"
                type="number"
                min="10"
                max="300"
                value={formData.timer}
                onChange={(e) => setFormData({ ...formData, timer: parseInt(e.target.value) })}
              />
            </div>

            <div className="flex gap-2 pt-4">
              <Button 
                onClick={handleStartRecording} 
                disabled={isLoading}
                className="flex-1"
              >
                {isLoading ? (
                  <>
                    <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    Starting...
                  </>
                ) : (
                  <>
                    <PlayIcon className="mr-2 h-4 w-4" />
                    Start Recording
                  </>
                )}
              </Button>
              <Button 
                variant="outline"
                onClick={() => setFormData({
                  url: 'https://example.com',
                  flowName: 'e.g., Login Flow',
                  timer: 30
                })}
              >
                Reset
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>
              Your latest recorded flows and test cases
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground text-center py-8">
              No recent activity. Start recording to see your flows here.
            </div>
          </CardContent>
        </Card>
      </div>
    </SidebarLayout>
  );
}
