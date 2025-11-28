import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  VideoIcon,
  FileText,
  PlayCircle,
  Sparkles,
  ArrowRight,
  Zap,
  Database,
  GitBranch
} from 'lucide-react';

const features = [
  {
    name: 'Recorder',
    description: 'Record user interactions and capture flow metadata',
    href: '/recorder',
    icon: VideoIcon,
    gradient: 'from-purple-500 to-pink-500',
    badge: 'Popular'
  },
  {
    name: 'Manual Tests',
    description: 'Generate manual test cases from recordings',
    href: '/manual-tests',
    icon: FileText,
    gradient: 'from-blue-500 to-cyan-500',
  },
  {
    name: 'Test Cases',
    description: 'AI-powered test case generation',
    href: '/test-cases',
    icon: Sparkles,
    gradient: 'from-violet-500 to-purple-500',
    badge: 'New'
  },
  {
    name: 'Agentic Flow',
    description: 'Automated test script generation with AI agents',
    href: '/agentic',
    icon: Zap,
    gradient: 'from-orange-500 to-red-500',
    badge: 'AI'
  },
  {
    name: 'Trial Runs',
    description: 'Execute and validate generated test scripts',
    href: '/trial-runs',
    icon: PlayCircle,
    gradient: 'from-green-500 to-emerald-500',
  },
  {
    name: 'Vector Search',
    description: 'Semantic search across your test data',
    href: '/vector-search',
    icon: Database,
    gradient: 'from-indigo-500 to-blue-500',
  },
];

const stats = [
  { name: 'Total Recordings', value: '12+', icon: VideoIcon },
  { name: 'Test Cases', value: '48', icon: FileText },
  { name: 'Success Rate', value: '95%', icon: Sparkles },
  { name: 'Integrations', value: '5', icon: GitBranch },
];

export function HomePageModern() {
  const navigate = useNavigate();

  return (
    <SidebarLayout>
      <div className="max-w-7xl mx-auto space-y-12">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center space-y-4"
        >
          <Badge variant="secondary" className="mb-4">
            <Sparkles className="mr-1 h-3 w-3" />
            AI-Powered Test Automation
          </Badge>
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
            Test Automation Studio
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Record user flows, generate test cases, and automate testing with AI-powered agents
          </p>
          <div className="flex gap-4 justify-center pt-4">
            <Button size="lg" onClick={() => navigate('/recorder')}>
              <VideoIcon className="mr-2 h-5 w-5" />
              Start Recording
            </Button>
            <Button size="lg" variant="outline" onClick={() => navigate('/dashboard')}>
              View Dashboard
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
          </div>
        </motion.div>

        {/* Stats */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="grid grid-cols-2 gap-4 lg:grid-cols-4"
        >
          {stats.map((stat, index) => (
            <Card key={stat.name}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">{stat.name}</p>
                    <p className="text-2xl font-bold">{stat.value}</p>
                  </div>
                  <stat.icon className="h-8 w-8 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          ))}
        </motion.div>

        {/* Features Grid */}
        <div className="space-y-4">
          <div className="text-center">
            <h2 className="text-3xl font-bold tracking-tight">Features</h2>
            <p className="text-muted-foreground mt-2">
              Everything you need to automate your testing workflow
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature, index) => (
              <motion.div
                key={feature.name}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.2 + index * 0.1 }}
              >
                <Card 
                  className="cursor-pointer hover:shadow-lg transition-all duration-300 hover:-translate-y-1"
                  onClick={() => navigate(feature.href)}
                >
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className={`p-3 rounded-lg bg-gradient-to-br ${feature.gradient}`}>
                        <feature.icon className="h-6 w-6 text-white" />
                      </div>
                      {feature.badge && (
                        <Badge variant="secondary">{feature.badge}</Badge>
                      )}
                    </div>
                    <CardTitle className="mt-4">{feature.name}</CardTitle>
                    <CardDescription>{feature.description}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button variant="ghost" className="w-full">
                      Get Started
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </Button>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Quick Actions */}
        <Card className="bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-950/20 dark:to-pink-950/20 border-purple-200 dark:border-purple-800">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5 text-purple-600" />
              Quick Start Guide
            </CardTitle>
            <CardDescription>
              Get up and running in minutes
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-600 text-white text-sm font-bold">1</div>
              <div>
                <p className="font-medium">Record a Flow</p>
                <p className="text-sm text-muted-foreground">Navigate to Recorder and capture user interactions</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-600 text-white text-sm font-bold">2</div>
              <div>
                <p className="font-medium">Generate Test Cases</p>
                <p className="text-sm text-muted-foreground">Use AI to automatically create manual or automated tests</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-purple-600 text-white text-sm font-bold">3</div>
              <div>
                <p className="font-medium">Execute & Validate</p>
                <p className="text-sm text-muted-foreground">Run trial tests and review results</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </SidebarLayout>
  );
}
