import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { FlowNode, NODE_DIMENSIONS } from './FlowNode';
import { ConnectionLine } from './ConnectionLine';
import { NodePopup } from './NodePopup';
import { FlowNodeData, ConnectionData, PopupData } from './types';
import {
  Lightbulb,
  Play,
  Video,
  FileText,
  Code2,
  Settings,
  Upload,
  GitBranch,
  Download,
  Workflow,
  Database,
  CheckCircle,
} from 'lucide-react';

interface ParallaxFlowCanvasProps {
  onNodeAction?: (nodeId: string, data: any) => void;
}

// Layout constants
const HORIZONTAL_SPACING = 400;
const VERTICAL_SPACING = 350;
const START_X = 200;
const START_Y = 300;

export const ParallaxFlowCanvas: React.FC<ParallaxFlowCanvasProps> = ({ onNodeAction }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollX, setScrollX] = useState(0);
  const [nodes, setNodes] = useState<Map<string, FlowNodeData>>(new Map());
  const [connections, setConnections] = useState<ConnectionData[]>([]);
  const [activePopup, setActivePopup] = useState<PopupData | null>(null);
  const [canvasWidth, setCanvasWidth] = useState(3000);

  // Initialize with Esan start node
  useEffect(() => {
    initializeFlow();
  }, []);

  const initializeFlow = () => {
    const initialNodes = new Map<string, FlowNodeData>();

    // Esan start node
    initialNodes.set('esan', {
      id: 'esan',
      type: 'start',
      label: 'ESAN',
      description: 'Test Automation Studio',
      status: 'revealed',
      position: { x: START_X, y: START_Y },
      color: 'blue',
      icon: <Lightbulb size={64} />,
      onAction: () => handleEsanClick(),
    });

    setNodes(initialNodes);
  };

  const handleEsanClick = () => {
    // Show progress animation (simulated)
    updateNodeStatus('esan', 'processing', 0);

    // Simulate progress
    let progress = 0;
    const interval = setInterval(() => {
      progress += 10;
      updateNodeStatus('esan', 'processing', progress);

      if (progress >= 100) {
        clearInterval(interval);
        updateNodeStatus('esan', 'completed');
        // Reveal Recorder and Execute choice nodes
        revealChoiceNodes();
      }
    }, 100);
  };

  const revealChoiceNodes = () => {
    const newNodes = new Map(nodes);

    // Recorder node (left branch)
    newNodes.set('recorder', {
      id: 'recorder',
      type: 'choice',
      label: 'Recorder',
      description: 'Record user flow',
      status: 'revealed',
      position: { x: START_X + HORIZONTAL_SPACING, y: START_Y - VERTICAL_SPACING / 2 },
      color: 'cyan',
      icon: <Video size={48} />,
      parentId: 'esan',
      onAction: () => handleRecorderClick(),
    });

    // Execute node (right branch)
    newNodes.set('execute', {
      id: 'execute',
      type: 'choice',
      label: 'Execute',
      description: 'Run test suites',
      status: 'revealed',
      position: { x: START_X + HORIZONTAL_SPACING, y: START_Y + VERTICAL_SPACING / 2 },
      color: 'purple',
      icon: <Play size={48} fill="currentColor" />,
      parentId: 'esan',
      onAction: () => handleExecuteClick(),
    });

    setNodes(newNodes);

    // Add connections
    const newConnections: ConnectionData[] = [
      {
        id: 'esan-recorder',
        fromNodeId: 'esan',
        toNodeId: 'recorder',
        direction: 'left',
        status: 'active',
      },
      {
        id: 'esan-execute',
        fromNodeId: 'esan',
        toNodeId: 'execute',
        direction: 'right',
        status: 'active',
      },
    ];

    setConnections(newConnections);
    expandCanvas();
  };

  const handleRecorderClick = () => {
    // Show popup for recorder input
    setActivePopup({
      nodeId: 'recorder',
      title: 'Start Recorder',
      fields: [
        {
          name: 'url',
          label: 'Website URL',
          type: 'text',
          placeholder: 'https://example.com',
          required: true,
        },
        {
          name: 'flowName',
          label: 'Flow Name',
          type: 'text',
          placeholder: 'My Test Flow',
          required: true,
        },
        {
          name: 'timer',
          label: 'Timer (seconds)',
          type: 'number',
          placeholder: '60',
          required: true,
        },
      ],
      onSubmit: (values) => handleRecorderSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handleRecorderSubmit = async (values: any) => {
    // Mark recorder as processing
    updateNodeStatus('recorder', 'processing', 0);

    // TODO: Call backend API to start recorder
    // For now, simulate the flow
    setTimeout(() => {
      updateNodeStatus('recorder', 'completed');
      revealRefineRecorderNode();
    }, 2000);
  };

  const revealRefineRecorderNode = () => {
    const newNodes = new Map(nodes);

    newNodes.set('refine-recorder', {
      id: 'refine-recorder',
      type: 'process',
      label: 'Refine Recorder',
      description: 'Processing flow...',
      status: 'processing',
      progress: 0,
      position: { x: START_X + HORIZONTAL_SPACING * 2, y: START_Y - VERTICAL_SPACING / 2 },
      color: 'blue',
      icon: <Settings size={48} />,
      parentId: 'recorder',
    });

    setNodes(newNodes);
    addConnection('recorder', 'refine-recorder', 'left');

    // Simulate ingestion progress
    simulateProgress('refine-recorder', () => {
      revealRecorderBranches();
    });
    
    expandCanvas();
  };

  const revealRecorderBranches = () => {
    const newNodes = new Map(nodes);

    // Manual branch
    newNodes.set('manual', {
      id: 'manual',
      type: 'action',
      label: 'Manual',
      description: 'Generate test cases',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 3,
        y: START_Y - VERTICAL_SPACING,
      },
      color: 'green',
      icon: <FileText size={48} />,
      parentId: 'refine-recorder',
      onAction: () => handleManualClick(),
    });

    // Automation branch
    newNodes.set('automation', {
      id: 'automation',
      type: 'action',
      label: 'Automation',
      description: 'Generate scripts',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 3,
        y: START_Y,
      },
      color: 'amber',
      icon: <Code2 size={48} />,
      parentId: 'refine-recorder',
      onAction: () => handleAutomationClick(),
    });

    setNodes(newNodes);
    addConnection('refine-recorder', 'manual', 'left');
    addConnection('refine-recorder', 'automation', 'left');
    
    expandCanvas();
  };

  const handleManualClick = () => {
    setActivePopup({
      nodeId: 'manual',
      title: 'Upload Test Template',
      fields: [
        {
          name: 'template',
          label: 'XLSX Template (Optional)',
          type: 'file',
          placeholder: 'Choose XLSX file',
          required: false,
        },
      ],
      onSubmit: (values) => handleManualSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handleManualSubmit = async (values: any) => {
    updateNodeStatus('manual', 'completed');

    // Add Test Processing node
    const newNodes = new Map(nodes);
    newNodes.set('test-processing', {
      id: 'test-processing',
      type: 'process',
      label: 'Test Processing',
      description: 'Generating test cases...',
      status: 'processing',
      progress: 0,
      position: {
        x: START_X + HORIZONTAL_SPACING * 4,
        y: START_Y - VERTICAL_SPACING,
      },
      color: 'green',
      icon: <Database size={48} />,
      parentId: 'manual',
    });

    setNodes(newNodes);
    addConnection('manual', 'test-processing', 'left');

    simulateProgress('test-processing', () => {
      revealExportTestResult();
    });
    
    expandCanvas();
  };

  const revealExportTestResult = () => {
    const newNodes = new Map(nodes);

    newNodes.set('export-test', {
      id: 'export-test',
      type: 'end',
      label: 'Export Test Result',
      description: 'Download XLSX',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 5,
        y: START_Y - VERTICAL_SPACING,
      },
      color: 'green',
      icon: <Download size={48} />,
      parentId: 'test-processing',
      onAction: () => handleDownloadTest(),
    });

    setNodes(newNodes);
    addConnection('test-processing', 'export-test', 'left');
    
    expandCanvas();
  };

  const handleDownloadTest = () => {
    updateNodeStatus('export-test', 'completed');
    alert('Test results downloaded!');
  };

  const handleAutomationClick = () => {
    setActivePopup({
      nodeId: 'automation',
      title: 'Repository Details',
      fields: [
        {
          name: 'repoUrl',
          label: 'Repository URL',
          type: 'text',
          placeholder: 'https://github.com/user/repo',
          required: true,
        },
        {
          name: 'branch',
          label: 'Branch',
          type: 'text',
          placeholder: 'main',
          required: false,
        },
      ],
      onSubmit: (values) => handleAutomationSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handleAutomationSubmit = async (values: any) => {
    updateNodeStatus('automation', 'processing', 0);

    // Simulate cloning
    simulateProgress('automation', () => {
      updateNodeStatus('automation', 'completed');
      revealRefineStepsNode();
    });
  };

  const revealRefineStepsNode = () => {
    const newNodes = new Map(nodes);

    newNodes.set('refine-steps', {
      id: 'refine-steps',
      type: 'action',
      label: 'Refine Steps',
      description: 'Review and edit',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 4,
        y: START_Y,
      },
      color: 'amber',
      icon: <Settings size={48} />,
      parentId: 'automation',
      onAction: () => handleRefineStepsClick(),
    });

    setNodes(newNodes);
    addConnection('automation', 'refine-steps', 'left');
    
    expandCanvas();
  };

  const handleRefineStepsClick = () => {
    // Show editable steps (for now, just complete it)
    updateNodeStatus('refine-steps', 'processing', 0);
    
    simulateProgress('refine-steps', () => {
      updateNodeStatus('refine-steps', 'completed');
      revealReviewScriptNode();
    });
  };

  const revealReviewScriptNode = () => {
    const newNodes = new Map(nodes);

    newNodes.set('review-script', {
      id: 'review-script',
      type: 'action',
      label: 'Review Script',
      description: 'Check generated code',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 5,
        y: START_Y,
      },
      color: 'amber',
      icon: <Code2 size={48} />,
      parentId: 'refine-steps',
      onAction: () => handleReviewScriptClick(),
    });

    setNodes(newNodes);
    addConnection('refine-steps', 'review-script', 'left');
    
    expandCanvas();
  };

  const handleReviewScriptClick = () => {
    updateNodeStatus('review-script', 'completed');
    revealTestExecutionDetails();
  };

  const revealTestExecutionDetails = () => {
    const newNodes = new Map(nodes);

    newNodes.set('test-execution', {
      id: 'test-execution',
      type: 'action',
      label: 'Test Execution',
      description: 'Configure and run',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 6,
        y: START_Y,
      },
      color: 'amber',
      icon: <Upload size={48} />,
      parentId: 'review-script',
      onAction: () => handleTestExecutionClick(),
    });

    setNodes(newNodes);
    addConnection('review-script', 'test-execution', 'left');
    
    expandCanvas();
  };

  const handleTestExecutionClick = () => {
    setActivePopup({
      nodeId: 'test-execution',
      title: 'Test Execution Details',
      fields: [
        {
          name: 'testCaseId',
          label: 'Test Case ID',
          type: 'text',
          placeholder: 'TC001',
          required: true,
        },
        {
          name: 'datasheet',
          label: 'Test Data (Optional)',
          type: 'file',
          placeholder: 'Choose file',
          required: false,
        },
      ],
      onSubmit: (values) => handleTestExecutionSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handleTestExecutionSubmit = async (values: any) => {
    updateNodeStatus('test-execution', 'processing', 0);

    simulateProgress('test-execution', () => {
      updateNodeStatus('test-execution', 'completed');
      revealTrialRunNode();
    });
  };

  const revealTrialRunNode = () => {
    const newNodes = new Map(nodes);

    newNodes.set('trial-run', {
      id: 'trial-run',
      type: 'process',
      label: 'Trial Run',
      description: 'Executing tests...',
      status: 'processing',
      progress: 0,
      position: {
        x: START_X + HORIZONTAL_SPACING * 7,
        y: START_Y,
      },
      color: 'amber',
      icon: <Workflow size={48} />,
      parentId: 'test-execution',
    });

    setNodes(newNodes);
    addConnection('test-execution', 'trial-run', 'left');

    simulateProgress('trial-run', () => {
      revealCompletionOptions();
    });
    
    expandCanvas();
  };

  const revealCompletionOptions = () => {
    const newNodes = new Map(nodes);

    // Push to Git option
    newNodes.set('push-git', {
      id: 'push-git',
      type: 'end',
      label: 'Push to Git',
      description: 'Commit changes',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 8,
        y: START_Y - VERTICAL_SPACING / 3,
      },
      color: 'rose',
      icon: <GitBranch size={48} />,
      parentId: 'trial-run',
      onAction: () => handlePushToGit(),
    });

    // Test Report option
    newNodes.set('test-report', {
      id: 'test-report',
      type: 'end',
      label: 'Test Report',
      description: 'Download report',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 8,
        y: START_Y + VERTICAL_SPACING / 3,
      },
      color: 'green',
      icon: <Download size={48} />,
      parentId: 'trial-run',
      onAction: () => handleDownloadReport(),
    });

    setNodes(newNodes);
    addConnection('trial-run', 'push-git', 'left');
    addConnection('trial-run', 'test-report', 'left');
    
    expandCanvas();
  };

  const handlePushToGit = () => {
    setActivePopup({
      nodeId: 'push-git',
      title: 'Push to Git',
      fields: [
        {
          name: 'branch',
          label: 'Branch Name',
          type: 'text',
          placeholder: 'main',
          required: true,
        },
        {
          name: 'commitMessage',
          label: 'Commit Message',
          type: 'textarea',
          placeholder: 'Add automated test scripts',
          required: true,
        },
      ],
      onSubmit: (values) => handlePushToGitSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handlePushToGitSubmit = async (values: any) => {
    updateNodeStatus('push-git', 'processing', 0);
    
    simulateProgress('push-git', () => {
      updateNodeStatus('push-git', 'completed');
      alert('Successfully pushed to Git!');
    });
  };

  const handleDownloadReport = () => {
    updateNodeStatus('test-report', 'completed');
    alert('Test report downloaded!');
  };

  const handleExecuteClick = () => {
    // Show Execute flow options
    const newNodes = new Map(nodes);

    // Manual Test Case Generation
    newNodes.set('execute-manual', {
      id: 'execute-manual',
      type: 'action',
      label: 'Manual Test Case',
      description: 'Generate from flow',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 2,
        y: START_Y + VERTICAL_SPACING / 2 - VERTICAL_SPACING / 3,
      },
      color: 'green',
      icon: <FileText size={48} />,
      parentId: 'execute',
      onAction: () => handleExecuteManualClick(),
    });

    // Automation Script Generation
    newNodes.set('execute-automation', {
      id: 'execute-automation',
      type: 'action',
      label: 'Automation Script',
      description: 'Generate from flow',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 2,
        y: START_Y + VERTICAL_SPACING / 2 + VERTICAL_SPACING / 3,
      },
      color: 'purple',
      icon: <Code2 size={48} />,
      parentId: 'execute',
      onAction: () => handleExecuteAutomationClick(),
    });

    setNodes(newNodes);
    addConnection('execute', 'execute-manual', 'right');
    addConnection('execute', 'execute-automation', 'right');
    updateNodeStatus('execute', 'completed');
    
    expandCanvas();
  };

  const handleExecuteManualClick = () => {
    setActivePopup({
      nodeId: 'execute-manual',
      title: 'Select Flow for Manual Tests',
      fields: [
        {
          name: 'flow',
          label: 'Existing Flow',
          type: 'select',
          options: [
            { value: 'flow1', label: 'Login Flow' },
            { value: 'flow2', label: 'Checkout Flow' },
            { value: 'flow3', label: 'Search Flow' },
          ],
          required: true,
        },
        {
          name: 'template',
          label: 'XLSX Template',
          type: 'file',
          placeholder: 'Choose template',
          required: true,
        },
      ],
      onSubmit: (values) => handleExecuteManualSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handleExecuteManualSubmit = async (values: any) => {
    updateNodeStatus('execute-manual', 'completed');
    // Continue with similar flow as manual branch
    // For brevity, showing simplified version
    alert('Execute Manual flow would continue...');
  };

  const handleExecuteAutomationClick = () => {
    setActivePopup({
      nodeId: 'execute-automation',
      title: 'Repository Details',
      fields: [
        {
          name: 'repoUrl',
          label: 'Repository URL',
          type: 'text',
          placeholder: 'https://github.com/user/repo',
          required: true,
        },
      ],
      onSubmit: (values) => handleExecuteAutomationSubmit(values),
      onCancel: () => setActivePopup(null),
    });
  };

  const handleExecuteAutomationSubmit = async (values: any) => {
    updateNodeStatus('execute-automation', 'processing', 0);
    
    simulateProgress('execute-automation', () => {
      updateNodeStatus('execute-automation', 'completed');
      // Continue with workflow selection
      alert('Execute Automation flow would continue...');
    });
  };

  // Utility functions
  const updateNodeStatus = (nodeId: string, status: FlowNodeData['status'], progress?: number) => {
    setNodes((prev) => {
      const newNodes = new Map(prev);
      const node = newNodes.get(nodeId);
      if (node) {
        node.status = status;
        if (progress !== undefined) {
          node.progress = progress;
        }
        newNodes.set(nodeId, { ...node });
      }
      return newNodes;
    });
  };

  const addConnection = (fromId: string, toId: string, direction: 'left' | 'right') => {
    setConnections((prev) => [
      ...prev,
      {
        id: `${fromId}-${toId}`,
        fromNodeId: fromId,
        toNodeId: toId,
        direction,
        status: 'active',
      },
    ]);
  };

  const simulateProgress = (nodeId: string, onComplete: () => void) => {
    let progress = 0;
    const interval = setInterval(() => {
      progress += 10;
      updateNodeStatus(nodeId, 'processing', progress);

      if (progress >= 100) {
        clearInterval(interval);
        updateNodeStatus(nodeId, 'completed');
        setTimeout(onComplete, 300);
      }
    }, 200);
  };

  const expandCanvas = () => {
    // Calculate required width based on rightmost node
    let maxX = 0;
    nodes.forEach((node) => {
      const nodeRight = node.position.x + NODE_DIMENSIONS.width;
      if (nodeRight > maxX) {
        maxX = nodeRight;
      }
    });
    setCanvasWidth(Math.max(maxX + 500, 3000));
  };

  // Parallax scroll handler
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const scrollLeft = e.currentTarget.scrollLeft;
    setScrollX(scrollLeft);
  };

  return (
    <div className="relative w-full h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 overflow-hidden">
      {/* Parallax Background Layers */}
      <div
        className="absolute inset-0 bg-gradient-to-br from-blue-950/20 via-purple-950/20 to-slate-950/20"
        style={{
          transform: `translateX(${-scrollX * 0.1}px)`,
        }}
      />

      {/* Floating particles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {[...Array(50)].map((_, i) => (
          <motion.div
            key={i}
            className="absolute w-1 h-1 bg-blue-400 rounded-full"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              transform: `translateX(${-scrollX * (0.05 + Math.random() * 0.1)}px)`,
            }}
            animate={{
              opacity: [0.2, 0.6, 0.2],
              scale: [1, 1.5, 1],
            }}
            transition={{
              duration: 3 + Math.random() * 2,
              repeat: Infinity,
              delay: Math.random() * 2,
            }}
          />
        ))}
      </div>

      {/* Scrollable Canvas */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="relative w-full h-full overflow-x-auto overflow-y-hidden scrollbar-thin scrollbar-thumb-blue-500/30 scrollbar-track-transparent"
        style={{
          scrollbarWidth: 'thin',
        }}
      >
        <div
          className="relative"
          style={{
            width: `${canvasWidth}px`,
            height: '100%',
            minHeight: '100vh',
          }}
        >
          {/* Connections Layer */}
          <div className="absolute inset-0 pointer-events-none">
            {connections.map((connection) => {
              const fromNode = nodes.get(connection.fromNodeId);
              const toNode = nodes.get(connection.toNodeId);

              if (!fromNode || !toNode) return null;

              return (
                <ConnectionLine
                  key={connection.id}
                  connection={connection}
                  fromPos={fromNode.position}
                  toPos={toNode.position}
                  nodeWidth={NODE_DIMENSIONS.width}
                  nodeHeight={NODE_DIMENSIONS.height}
                />
              );
            })}
          </div>

          {/* Nodes Layer */}
          {Array.from(nodes.values()).map((node) => (
            <FlowNode key={node.id} node={node} onClick={node.onAction} />
          ))}
        </div>
      </div>

      {/* Popup Layer */}
      <NodePopup popup={activePopup} onClose={() => setActivePopup(null)} />

      {/* Instructions */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 1 }}
        className="fixed bottom-8 left-1/2 -translate-x-1/2 px-6 py-3 bg-black/40 backdrop-blur-md border border-white/10 rounded-full text-white text-sm"
      >
        Click on nodes to progress through the workflow
      </motion.div>
    </div>
  );
};
