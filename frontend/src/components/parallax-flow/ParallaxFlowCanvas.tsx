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
  RefreshCw,
  FileCheck,
  PlayCircle,
} from 'lucide-react';

interface ParallaxFlowCanvasProps {
  onNodeAction?: (nodeId: string, data: any) => void;
}

// Layout constants
const HORIZONTAL_SPACING = 400;
const START_X = 300;
const START_Y = 400; // Center Y position for horizontal line
const LAYER_PARALLAX_FACTOR = [0.3, 0.6, 1.0]; // Parallax speed for each layer

export const ParallaxFlowCanvas: React.FC<ParallaxFlowCanvasProps> = ({ onNodeAction }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollX, setScrollX] = useState(0);
  const [nodes, setNodes] = useState<Map<string, FlowNodeData>>(new Map());
  const [connections, setConnections] = useState<ConnectionData[]>([]);
  const [activePopup, setActivePopup] = useState<PopupData | null>(null);
  const [canvasWidth, setCanvasWidth] = useState(4000);
  const [mainCharacterNodeId, setMainCharacterNodeId] = useState<string | null>(null);
  const [flowData, setFlowData] = useState<any>({});

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
      layer: 1,
      color: 'blue',
      icon: <Lightbulb size={64} />,
      flowType: 'neutral',
      onAction: () => handleEsanClick(),
    });

    setNodes(initialNodes);
    setMainCharacterNodeId('esan');
  };

  const handleEsanClick = () => {
    setMainCharacterNodeId('esan');
    
    // Show progress animation
    updateNodeStatus('esan', 'processing', 0);

    // Simulate progress
    let progress = 0;
    const interval = setInterval(() => {
      progress += 10;
      updateNodeStatus('esan', 'processing', progress);

      if (progress >= 100) {
        clearInterval(interval);
        updateNodeStatus('esan', 'completed');
        setTimeout(() => {
          revealChoiceNodes();
        }, 300);
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
      position: { x: START_X + HORIZONTAL_SPACING, y: START_Y },
      layer: 1,
      color: 'cyan',
      icon: <Video size={56} />,
      parentId: 'esan',
      flowType: 'recorder',
      onAction: () => handleRecorderClick(),
    });

    // Execute node (right branch) - placeholder for now
    newNodes.set('execute', {
      id: 'execute',
      type: 'choice',
      label: 'Execute',
      description: 'Run test suites',
      status: 'revealed',
      position: { x: START_X + HORIZONTAL_SPACING, y: START_Y },
      layer: 1,
      color: 'purple',
      icon: <Play size={56} fill="currentColor" />,
      parentId: 'esan',
      flowType: 'execute',
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
        flowType: 'recorder',
      },
      {
        id: 'esan-execute',
        fromNodeId: 'esan',
        toNodeId: 'execute',
        direction: 'right',
        status: 'active',
        flowType: 'execute',
      },
    ];

    setConnections(newConnections);
    expandCanvas();
  };

  // ==================== RECORDER FLOW ====================

  const handleRecorderClick = () => {
    setMainCharacterNodeId('recorder');
    scrollToNode('recorder');
    
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
    setActivePopup(null);
    
    // Store flow data
    setFlowData((prev: any) => ({ ...prev, recorder: values }));
    
    // Mark recorder as processing
    updateNodeStatus('recorder', 'processing', 0);

    // Simulate recording process
    let progress = 0;
    const interval = setInterval(() => {
      progress += 5;
      updateNodeStatus('recorder', 'processing', progress);

      if (progress >= 100) {
        clearInterval(interval);
        updateNodeStatus('recorder', 'completed');
        setTimeout(() => {
          revealRefineRecorderNode();
        }, 300);
      }
    }, 200);
  };

  const revealRefineRecorderNode = () => {
    const newNodes = new Map(nodes);

    newNodes.set('refine-recorder', {
      id: 'refine-recorder',
      type: 'process',
      label: 'Refine Recorder',
      description: 'Ingesting to vector DB...',
      status: 'processing',
      progress: 0,
      position: { x: START_X + HORIZONTAL_SPACING * 2, y: START_Y },
      layer: 1,
      color: 'blue',
      icon: <RefreshCw size={56} />,
      parentId: 'recorder',
      flowType: 'recorder',
    });

    setNodes(newNodes);
    addConnection('recorder', 'refine-recorder', 'left', 'recorder');
    setMainCharacterNodeId('refine-recorder');
    scrollToNode('refine-recorder');

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
        y: START_Y,
      },
      layer: 1,
      color: 'green',
      icon: <FileText size={56} />,
      parentId: 'refine-recorder',
      flowType: 'recorder',
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
      layer: 1,
      color: 'amber',
      icon: <Code2 size={56} />,
      parentId: 'refine-recorder',
      flowType: 'recorder',
      onAction: () => handleAutomationClick(),
    });

    setNodes(newNodes);
    addConnection('refine-recorder', 'manual', 'left', 'recorder');
    addConnection('refine-recorder', 'automation', 'left', 'recorder');
    
    expandCanvas();
  };

  // ===== MANUAL BRANCH =====

  const handleManualClick = () => {
    setMainCharacterNodeId('manual');
    scrollToNode('manual');
    
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
    setActivePopup(null);
    setFlowData((prev: any) => ({ ...prev, manual: values }));
    
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
        y: START_Y,
      },
      layer: 1,
      color: 'green',
      icon: <Database size={56} />,
      parentId: 'manual',
      flowType: 'recorder',
    });

    setNodes(newNodes);
    addConnection('manual', 'test-processing', 'left', 'recorder');
    setMainCharacterNodeId('test-processing');
    scrollToNode('test-processing');

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
        y: START_Y,
      },
      layer: 1,
      color: 'green',
      icon: <Download size={56} />,
      parentId: 'test-processing',
      flowType: 'recorder',
      onAction: () => handleDownloadTest(),
    });

    setNodes(newNodes);
    addConnection('test-processing', 'export-test', 'left', 'recorder');
    setMainCharacterNodeId('export-test');
    scrollToNode('export-test');
    
    expandCanvas();
  };

  const handleDownloadTest = () => {
    updateNodeStatus('export-test', 'completed');
    alert('Test results downloaded! (Manual flow complete)');
    setMainCharacterNodeId('export-test');
  };

  // ===== AUTOMATION BRANCH =====

  const handleAutomationClick = () => {
    setMainCharacterNodeId('automation');
    scrollToNode('automation');
    
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
          label: 'Branch (optional)',
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
    setActivePopup(null);
    setFlowData((prev: any) => ({ ...prev, automation: values }));
    
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
      description: 'Review and edit flow',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 4,
        y: START_Y,
      },
      layer: 1,
      color: 'amber',
      icon: <FileCheck size={56} />,
      parentId: 'automation',
      flowType: 'recorder',
      onAction: () => handleRefineStepsClick(),
    });

    setNodes(newNodes);
    addConnection('automation', 'refine-steps', 'left', 'recorder');
    setMainCharacterNodeId('refine-steps');
    scrollToNode('refine-steps');
    
    expandCanvas();
  };

  const handleRefineStepsClick = () => {
    setMainCharacterNodeId('refine-steps');
    scrollToNode('refine-steps');
    
    // For now, just auto-complete
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
      layer: 1,
      color: 'amber',
      icon: <Code2 size={56} />,
      parentId: 'refine-steps',
      flowType: 'recorder',
      onAction: () => handleReviewScriptClick(),
    });

    setNodes(newNodes);
    addConnection('refine-steps', 'review-script', 'left', 'recorder');
    setMainCharacterNodeId('review-script');
    scrollToNode('review-script');
    
    expandCanvas();
  };

  const handleReviewScriptClick = () => {
    setMainCharacterNodeId('review-script');
    updateNodeStatus('review-script', 'completed');
    setTimeout(() => {
      revealTestExecutionDetails();
    }, 500);
  };

  const revealTestExecutionDetails = () => {
    const newNodes = new Map(nodes);

    newNodes.set('test-execution', {
      id: 'test-execution',
      type: 'action',
      label: 'Test Execution Details',
      description: 'Configure test run',
      status: 'revealed',
      position: {
        x: START_X + HORIZONTAL_SPACING * 6,
        y: START_Y,
      },
      layer: 1,
      color: 'amber',
      icon: <Upload size={56} />,
      parentId: 'review-script',
      flowType: 'recorder',
      onAction: () => handleTestExecutionClick(),
    });

    setNodes(newNodes);
    addConnection('review-script', 'test-execution', 'left', 'recorder');
    setMainCharacterNodeId('test-execution');
    scrollToNode('test-execution');
    
    expandCanvas();
  };

  const handleTestExecutionClick = () => {
    setMainCharacterNodeId('test-execution');
    scrollToNode('test-execution');
    
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
    setActivePopup(null);
    setFlowData((prev: any) => ({ ...prev, testExecution: values }));
    
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
      layer: 1,
      color: 'amber',
      icon: <PlayCircle size={56} />,
      parentId: 'test-execution',
      flowType: 'recorder',
    });

    setNodes(newNodes);
    addConnection('test-execution', 'trial-run', 'left', 'recorder');
    setMainCharacterNodeId('trial-run');
    scrollToNode('trial-run');

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
        y: START_Y,
      },
      layer: 1,
      color: 'rose',
      icon: <GitBranch size={56} />,
      parentId: 'trial-run',
      flowType: 'recorder',
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
        y: START_Y,
      },
      layer: 1,
      color: 'green',
      icon: <Download size={56} />,
      parentId: 'trial-run',
      flowType: 'recorder',
      onAction: () => handleDownloadReport(),
    });

    setNodes(newNodes);
    addConnection('trial-run', 'push-git', 'left', 'recorder');
    addConnection('trial-run', 'test-report', 'left', 'recorder');
    
    expandCanvas();
  };

  const handlePushToGit = () => {
    setMainCharacterNodeId('push-git');
    scrollToNode('push-git');
    
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
    setActivePopup(null);
    updateNodeStatus('push-git', 'processing', 0);
    
    simulateProgress('push-git', () => {
      updateNodeStatus('push-git', 'completed');
      alert('Successfully pushed to Git! (Recorder flow complete)');
    });
  };

  const handleDownloadReport = () => {
    setMainCharacterNodeId('test-report');
    scrollToNode('test-report');
    updateNodeStatus('test-report', 'completed');
    alert('Test report downloaded! (Recorder flow complete)');
  };

  // ==================== EXECUTE FLOW (Placeholder) ====================

  const handleExecuteClick = () => {
    setMainCharacterNodeId('execute');
    scrollToNode('execute');
    alert('Execute flow - Coming soon! (Will be implemented next)');
  };

  // ==================== UTILITY FUNCTIONS ====================

  const scrollToNode = (nodeId: string) => {
    const node = nodes.get(nodeId);
    if (!node || !containerRef.current) return;

    // Calculate target scroll position to center the node
    const targetX = node.position.x - (containerRef.current.clientWidth / 2) + (NODE_DIMENSIONS.width / 2);
    
    containerRef.current.scrollTo({
      left: Math.max(0, targetX),
      behavior: 'smooth',
    });
  };

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

  const addConnection = (fromId: string, toId: string, direction: 'left' | 'right', flowType: 'recorder' | 'execute' | 'neutral') => {
    setConnections((prev) => [
      ...prev,
      {
        id: `${fromId}-${toId}`,
        fromNodeId: fromId,
        toNodeId: toId,
        direction,
        status: 'active',
        flowType,
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
    setCanvasWidth(Math.max(maxX + 600, 4000));
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
          transform: `translateX(${-scrollX * 0.2}px)`,
          transition: 'transform 0.1s ease-out',
        }}
      />

      {/* Floating particles - Background layer */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {[...Array(80)].map((_, i) => {
          const layer = i % 3;
          return (
            <motion.div
              key={i}
              className="absolute rounded-full"
              style={{
                left: `${(i * 13) % 100}%`,
                top: `${(i * 17) % 100}%`,
                width: `${2 + layer}px`,
                height: `${2 + layer}px`,
                background: layer === 2 
                  ? 'radial-gradient(circle, rgba(168, 85, 247, 0.6) 0%, transparent 70%)'
                  : 'radial-gradient(circle, rgba(59, 130, 246, 0.4) 0%, transparent 70%)',
                transform: `translateX(${-scrollX * LAYER_PARALLAX_FACTOR[layer]}px)`,
                filter: 'blur(1px)',
              }}
              animate={{
                y: [0, -30, 0],
                opacity: [0.3, 0.7, 0.3],
                scale: [1, 1.2, 1],
              }}
              transition={{
                duration: 5 + Math.random() * 3,
                repeat: Infinity,
                delay: Math.random() * 2,
                ease: 'easeInOut',
              }}
            />
          );
        })}
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
          {/* Connections Layer - moves with middle layer parallax */}
          <div 
            className="absolute inset-0 pointer-events-none"
            style={{
              transform: `translateX(${-scrollX * 0.3}px)`,
            }}
          >
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
                  scrollX={scrollX}
                />
              );
            })}
          </div>

          {/* Nodes Layer - full speed parallax */}
          {Array.from(nodes.values()).map((node) => (
            <div
              key={node.id}
              style={{
                position: 'absolute',
                left: 0,
                top: 0,
                transform: `translateX(${-scrollX * (1 - LAYER_PARALLAX_FACTOR[node.layer])}px)`,
              }}
            >
              <FlowNode 
                node={node} 
                onClick={node.onAction}
                isMainCharacter={mainCharacterNodeId === node.id}
              />
            </div>
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
        className="fixed bottom-8 left-1/2 -translate-x-1/2 px-6 py-3 bg-black/40 backdrop-blur-md border border-white/10 rounded-full text-white text-sm z-50"
      >
        🎯 Click on nodes to progress • Scroll to explore the flow
      </motion.div>

      {/* Flow Status */}
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 1.5 }}
        className="fixed top-8 left-8 px-6 py-3 bg-black/40 backdrop-blur-md border border-white/10 rounded-xl text-white text-sm z-50"
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" />
          <span className="font-semibold">Recorder Flow Active</span>
        </div>
      </motion.div>
    </div>
  );
};
