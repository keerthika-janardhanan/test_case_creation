import { useState } from 'react';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Upload, FileText, Download } from 'lucide-react';
import { toast } from 'sonner';

export function ManualTestsPage() {
  const [isLoading, setIsLoading] = useState(false);

  return (
    <SidebarLayout>
      <div className="max-w-7xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Manual Test Cases</h1>
          <p className="text-muted-foreground mt-2">
            Generate manual test cases from recorded flows
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Upload Flow */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Upload className="h-5 w-5" />
                Upload Recording
              </CardTitle>
              <CardDescription>
                Upload a recorded flow file to generate test cases
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="flowFile">Flow File (JSON)</Label>
                <Input id="flowFile" type="file" accept=".json" />
              </div>
              <Button className="w-full" disabled={isLoading}>
                <Upload className="mr-2 h-4 w-4" />
                Upload & Generate
              </Button>
            </CardContent>
          </Card>

          {/* Generate from Session */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                From Session
              </CardTitle>
              <CardDescription>
                Generate test cases from an existing recording session
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="sessionId">Session ID</Label>
                <Input id="sessionId" placeholder="Enter session ID" />
              </div>
              <Button className="w-full" disabled={isLoading}>
                <FileText className="mr-2 h-4 w-4" />
                Generate Test Cases
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Generated Test Cases */}
        <Card>
          <CardHeader>
            <CardTitle>Generated Test Cases</CardTitle>
            <CardDescription>
              Manual test cases generated from your recordings
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No test cases generated yet</p>
              <p className="text-sm">Upload a recording or select a session to get started</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </SidebarLayout>
  );
}
