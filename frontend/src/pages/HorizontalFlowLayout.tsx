import { motion, AnimatePresence } from 'framer-motion';
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { startRecorder, stopRecorder, getRecorderStatus, finalizeRecorderBySession, buildArtifactUrl } from '../api/recorder';
import { generateTestCases, generateTestCasesWithTemplate } from '../api/testCases';
import { buildWebSocketUrl, API_BASE_URL } from '../api/client';
import { previewAgentic, generatePayload, payloadAgenticStream, uploadDatasheet, listDatasheets, persistFiles, trialRunAgenticStream, keywordInspect, renameTestCaseId } from '../api/agentic';
import { ingestJira, ingestWebsite, ingestDocuments, deleteVectorDoc, deleteVectorSource, queryVectorAll, type VectorDocument } from '../api/ingest';
import { pushToGit } from '../api/git';
import { ExecuteFlow } from '../components/design-flow/ExecuteFlow';
import { 
  Lightbulb, 
  Play, 
  Circle, 
  FileText, 
  Code2, 
  Loader2,
  CheckCircle2,
  Upload,
  Search,
  ArrowLeft,
  Clock,
  Globe,
  AlertCircle,
  Settings,
  Database,
  BookOpen,
  FileSearch,
  ChevronDown,
  ChevronUp,
  GitBranch,
  Edit2,
  Save,
  X
} from 'lucide-react';

type FlowStep = 
  | 'home' 
  | 'admin-home'
  | 'admin-jira'
  | 'admin-website'
  | 'admin-documents'
  | 'admin-vector'
  | 'recorder-start' 
  | 'recorder-active'
  | 'choice'
  | 'execute-choice'
  | 'manual-test'
  | 'manual-success'
  | 'manual-next-choice'
  | 'automation-repo-input'
  | 'automation-checking'
  | 'automation-script-choice'
  | 'automation-existing-preview'
  | 'automation-refined-preview'
  | 'automation-generated-script'
  | 'automation-testmanager-upload'
  | 'automation-trial-run'
  | 'automation-completion-choice'
  | 'completion';

interface HorizontalFlowLayoutProps {
  initialStep?: FlowStep;
}

export function HorizontalFlowLayout({ initialStep = 'home' }: HorizontalFlowLayoutProps) {
  const [currentStep, setCurrentStep] = useState<FlowStep>(initialStep);
  const [sessionName, setSessionName] = useState('');
  const [url, setUrl] = useState('');
  const [timer, setTimer] = useState('60');
  const [isRecording, setIsRecording] = useState(false);
  const [recordingStatus, setRecordingStatus] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [eventMessages, setEventMessages] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState<'manual' | 'automation' | null>(null);
  const [completedPaths, setCompletedPaths] = useState<Set<'manual' | 'automation'>>(new Set()); // Track completed workflows
  const [wasRunning, setWasRunning] = useState(false); // Track if recorder was previously running
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [generatingTestCases, setGeneratingTestCases] = useState(false);
  const [testCaseResults, setTestCaseResults] = useState<any>(null);
  const [ingestionStatus, setIngestionStatus] = useState<'pending' | 'success' | 'error' | null>(null);
  const [ingestionMessage, setIngestionMessage] = useState<string>('');
  const [sessionArtifacts, setSessionArtifacts] = useState<any>(null);
  
  // Automation workflow state
  const [repoUrl, setRepoUrl] = useState('');
  const [testKeyword, setTestKeyword] = useState('');
  const [existingScripts, setExistingScripts] = useState<any[]>([]);
  const [selectedScriptType, setSelectedScriptType] = useState<'existing' | 'refined' | null>(null);
  const [generatedScript, setGeneratedScript] = useState<string>('');
  const [testManagerFile, setTestManagerFile] = useState<File | null>(null);
  const [trialRunning, setTrialRunning] = useState(false);
  const [trialResult, setTrialResult] = useState<any>(null);
  const [refinedFlowSteps, setRefinedFlowSteps] = useState<any[]>([]);
  const [editableFlowPreview, setEditableFlowPreview] = useState<string>('');
  const [streamingPreview, setStreamingPreview] = useState(false);
  const [streamingPayload, setStreamingPayload] = useState(false);
  const [payloadProgress, setPayloadProgress] = useState<string>('');
  const [payloadFiles, setPayloadFiles] = useState<any[]>([]);
  
  // TestManager fields
  const [testCaseId, setTestCaseId] = useState<string>('');
  const [testCaseDescription, setTestCaseDescription] = useState<string>('');
  const [datasheetName, setDatasheetName] = useState<string>('');
  const [executeValue, setExecuteValue] = useState<string>('Yes');
  const [referenceId, setReferenceId] = useState<string>('');
  const [idName, setIdName] = useState<string>('');
  const [availableTestCaseIds, setAvailableTestCaseIds] = useState<string[]>([]);
  const [availableDatasheets, setAvailableDatasheets] = useState<string[]>([]);
  const [isNewTestCaseId, setIsNewTestCaseId] = useState(false);
  const [codeExpanded, setCodeExpanded] = useState(false);
  const [fullCodeContent, setFullCodeContent] = useState<string>('');
  const [loadingFullCode, setLoadingFullCode] = useState(false);
  const [datasheetFile, setDatasheetFile] = useState<File | null>(null);
  const [persisting, setPersisting] = useState(false);
  const [trialLogs, setTrialLogs] = useState<string>('');
  const [persistSuccess, setPersistSuccess] = useState<{filesCount: number; message: string} | null>(null);
  const [persistError, setPersistError] = useState<string | null>(null);
  
  // Git push state
  const [gitBranch, setGitBranch] = useState<string>('main');
  const [gitCommitMessage, setGitCommitMessage] = useState<string>('Add automated test scripts');
  const [gitPushing, setGitPushing] = useState<boolean>(false);
  const [gitPushResult, setGitPushResult] = useState<{success: boolean; message: string} | null>(null);
  
  // TestCaseID editing state
  const [editingTestCaseId, setEditingTestCaseId] = useState<string | null>(null);
  const [editedTestCaseIdValue, setEditedTestCaseIdValue] = useState<string>('');
  const [renamingTestCaseId, setRenamingTestCaseId] = useState<boolean>(false);
  const [renameResult, setRenameResult] = useState<{success: boolean; message: string} | null>(null);
  
  // Admin panel state
  const [jiraJql, setJiraJql] = useState<string>('');
  const [websiteUrl, setWebsiteUrl] = useState<string>('');
  const [websiteMaxDepth, setWebsiteMaxDepth] = useState<number>(3);
  const [documentFiles, setDocumentFiles] = useState<File[]>([]);
  const [vectorDocs, setVectorDocs] = useState<VectorDocument[]>([]);
  const [selectedDocIds, setSelectedDocIds] = useState<Set<string>>(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(50);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminSuccess, setAdminSuccess] = useState<string | null>(null);
  const [adminError, setAdminError] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const datasheetInputRef = useRef<HTMLInputElement>(null);
  const testManagerInputRef = useRef<HTMLInputElement>(null);
  const documentInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  // WebSocket connection for live events (optional - non-blocking)
  useEffect(() => {
    if (!activeSessionId) return;

    const wsUrl = buildWebSocketUrl(`/ws/recorder/${activeSessionId}`);
    console.log('Attempting WebSocket connection:', wsUrl);
    
    let ws: WebSocket | null = null;
    
    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected for session:', activeSessionId);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const message = data.message || JSON.stringify(data);
          setEventMessages(prev => [...prev, message]);
          
          // Update status based on event type
          if (data.type === 'launch-completed' || data.type === 'launch-stopped') {
            setIsRecording(false);
            setRecordingStatus('Recording completed! Processing...');
            setTimeout(() => setCurrentStep('choice'), 2000);
          } else if (data.type === 'status-update') {
            setRecordingStatus(message);
          }
        } catch (err) {
          console.error('WebSocket message error:', err);
        }
      };

      ws.onerror = (error) => {
        console.warn('WebSocket connection failed (non-critical):', error);
        // WebSocket failure is non-critical - polling will continue to work
      };

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
      };
    } catch (error) {
      console.warn('Failed to create WebSocket (non-critical):', error);
    }

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [activeSessionId]);

  // Particle background
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({ 
        x: (e.clientX / window.innerWidth - 0.5) * 2,
        y: (e.clientY / window.innerHeight - 0.5) * 2,
      });
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // Load vector documents when entering admin-vector screen
  useEffect(() => {
    if (currentStep === 'admin-vector') {
      (async () => {
        setAdminLoading(true);
        try {
          const result = await queryVectorAll(1000);
          setVectorDocs(result.results || []);
        } catch (error: any) {
          setAdminError(error.message || 'Failed to load vector documents');
        } finally {
          setAdminLoading(false);
        }
      })();
    }
    
    // Clear admin messages when changing screens
    if (!currentStep.startsWith('admin-')) {
      setAdminSuccess(null);
      setAdminError(null);
    }
  }, [currentStep]);

  const handleDesignClick = () => {
    setCurrentStep('recorder-start');
  };

  const handleExecuteClick = () => {
    // Show execute flow selection screen
    setCurrentStep('execute-choice');
  };

  const handleExecuteManualSelect = async (flowSlug: string) => {
    // Load the selected flow from vector DB and proceed to manual test generation
    // Use flowSlug as the identifier
    setActiveSessionId(flowSlug);
    setSessionName(flowSlug);
    setTestKeyword(flowSlug);
    
    console.log('[Execute] Selected flow for manual tests:', flowSlug);
    setCurrentStep('manual-test');
  };

  const handleExecuteAutomationSelect = async (flowSlug: string) => {
    // Load the selected flow from vector DB and proceed to automation flow
    // Use flowSlug as the identifier
    setActiveSessionId(flowSlug);
    setSessionName(flowSlug);
    setTestKeyword(flowSlug); // Auto-populate keyword
    
    console.log('[Execute] Selected flow for automation:', flowSlug);
    setCurrentStep('automation-repo-input');
  };

  const handleStartRecording = async () => {
    if (!sessionName || !url) {
      alert('Please fill in Flow Name and URL');
      return;
    }

    try {
      setIsRecording(true);
      setRecordingStatus('Launching Playwright Chromium browser...');
      setCurrentStep('recorder-active');
      setEventMessages([]);

      console.log('Starting recorder with:', {
        url: url.trim(),
        sessionName: sessionName.trim(),
        options: {
          flowName: sessionName.trim(),
          timeout: parseInt(timer) || 60,
        }
      });

      // Start recording via backend API using the recorder module
      const response = await startRecorder({
        url: url.trim(),
        sessionName: sessionName.trim(),
        options: {
          flowName: sessionName.trim(),
          timeout: parseInt(timer) || 60,
        },
      });

      console.log('Recorder started:', response);
      setActiveSessionId(response.sessionId);
      setRecordingStatus(`Session started: ${response.sessionId}. Browser launched!`);

      // Auto-stop after timer expires
      const timeoutSeconds = parseInt(timer) || 60;
      const autoStopTimeout = setTimeout(async () => {
        console.log(`Auto-stopping recorder after ${timeoutSeconds} seconds`);
        setRecordingStatus(`Recording time expired (${timeoutSeconds}s). Stopping automatically...`);
        await handleStopRecording();
      }, timeoutSeconds * 1000);

      // Store timeout ID to clear it if manually stopped
      (window as any).__recorderAutoStopTimeout = autoStopTimeout;

      // Poll for status updates
      const pollStatus = async () => {
        if (!response.sessionId) return;
        
        try {
          const status = await getRecorderStatus(response.sessionId);
          console.log('Status update:', status);
          
          // Detect transition from running to stopped
          const currentlyRunning = status.isRunning === true || status.status === 'running' || status.status === 'active';
          
          if (!currentlyRunning && wasRunning) {
            // Process just stopped - trigger finalization
            console.log('[AutoStop] Recorder process stopped, triggering finalization');
            setIsRecording(false);
            setRecordingStatus('Recording completed! Finalizing and ingesting...');
            setIngestionStatus('pending');
            setIngestionMessage('Refining and ingesting flow into vector DB...');
            
            try {
              const finalizeResult = await finalizeRecorderBySession(response.sessionId);
              console.log('[AutoStop] Finalization result:', finalizeResult);
              
              // Fetch session artifacts
              const artifacts = await getRecorderStatus(response.sessionId);
              setSessionArtifacts(artifacts);
              
              if (finalizeResult.status === 'processing') {
                setIngestionStatus('success');
                setIngestionMessage('Refinement and ingestion started in background');
              } else {
                setIngestionStatus('success');
                setIngestionMessage('Finalization completed');
              }
            } catch (finalizeError: any) {
              console.error('[AutoStop] Finalization error:', finalizeError);
              setIngestionStatus('error');
              setIngestionMessage('Finalization failed: ' + (finalizeError?.message || 'Unknown error'));
            }
            
            // Move to choice screen
            setTimeout(() => setCurrentStep('choice'), 2000);
            return; // Stop polling
          }
          
          // Update tracking state
          setWasRunning(currentlyRunning);
          
          if (status.status === 'completed' || status.status === 'stopped') {
            setIsRecording(false);
            setRecordingStatus('Recording completed! Finalizing and ingesting...');
            setIngestionStatus('pending');
            setIngestionMessage('Refining and ingesting flow into vector DB...');
            
            try {
              const finalizeResult = await finalizeRecorderBySession(response.sessionId);
              console.log('[AutoStop] Finalization result:', finalizeResult);
              
              // Fetch session artifacts
              const artifacts = await getRecorderStatus(response.sessionId);
              setSessionArtifacts(artifacts);
              
              if (finalizeResult.status === 'processing') {
                setIngestionStatus('success');
                setIngestionMessage('Refinement and ingestion started in background');
              } else {
                setIngestionStatus('success');
                setIngestionMessage('Finalization completed');
              }
            } catch (finalizeError: any) {
              console.error('[AutoStop] Finalization error:', finalizeError);
              setIngestionStatus('error');
              setIngestionMessage('Finalization failed: ' + (finalizeError?.message || 'Unknown error'));
            }
            
            // Move to choice screen
            setTimeout(() => setCurrentStep('choice'), 2000);
          } else if (currentlyRunning) {
            setRecordingStatus(`Recording... Interact with the browser to capture your flow`);
            setTimeout(pollStatus, 3000);
          } else {
            setTimeout(pollStatus, 3000);
          }
        } catch (err) {
          console.error('Status poll error:', err);
          setTimeout(pollStatus, 3000);
        }
      };
      
      // Initialize tracking
      setWasRunning(true);

      setTimeout(pollStatus, 3000);

    } catch (error: any) {
      console.error('Recording error:', error);
      console.error('Error details:', error.response?.data);
      console.error('Error status:', error.response?.status);
      console.error('Error message:', error.message);
      setIsRecording(false);
      setRecordingStatus('');
      setActiveSessionId(null);
      
      let errorMessage = 'Failed to start recording. ';
      
      if (error.code === 'ECONNREFUSED' || error.message?.includes('Network Error')) {
        errorMessage += 'Cannot connect to backend at http://localhost:8001. Please make sure the backend server is running.';
      } else if (error.response?.status === 500) {
        errorMessage += `Server error: ${error.response?.data?.detail || 'Internal server error'}`;
      } else if (error.response?.data?.detail) {
        errorMessage += error.response.data.detail;
      } else if (error.message) {
        errorMessage += error.message;
      } else {
        errorMessage += 'Unknown error occurred';
      }
      
      alert(errorMessage);
      setCurrentStep('recorder-start');
    }
  };

  const handleStopRecording = async () => {
    if (!activeSessionId) return;

    try {
      console.log('[Stop] Stopping recorder for session:', activeSessionId);
      setRecordingStatus('Stopping recorder...');
      await stopRecorder(activeSessionId);
      
      console.log('[Stop] Recorder stopped, starting finalization...');
      setRecordingStatus('Recording stopped successfully!');
      
      // Finalize the recording session (refine + ingest) - runs in background on server
      setIngestionStatus('pending');
      setIngestionMessage('Refining and ingesting flow into vector DB (processing in background)...');
      
      console.log('[Finalize] Calling finalizeRecorderBySession for:', activeSessionId);
      finalizeRecorderBySession(activeSessionId)
        .then(async (result: any) => {
          console.log('Finalize result:', result);
          
          // Fetch session artifacts
          try {
            const artifacts = await getRecorderStatus(activeSessionId);
            console.log('[Artifacts] Fetched session artifacts:', artifacts);
            setSessionArtifacts(artifacts);
          } catch (err) {
            console.warn('[Artifacts] Could not fetch session artifacts:', err);
          }
          
          // Backend now processes in background, just acknowledge it started
          if (result.status === 'processing') {
            setIngestionStatus('success');
            setIngestionMessage('Refinement and ingestion started. Check saved_flows/ directory for results.');
            setRecordingStatus('Recording saved. Processing in background...');
          } else if (result.autoIngest?.status === 'success') {
            setIngestionStatus('success');
            setIngestionMessage('Flow successfully refined and ingested into vector DB!');
            setRecordingStatus('Flow refined and ingested into vector DB!');
          } else if (result.autoIngest?.status === 'error') {
            setIngestionStatus('error');
            const errorMsg = result.autoIngest?.error || 'Unknown error';
            setIngestionMessage(`Refinement failed: ${errorMsg}`);
            console.warn('Auto-ingest error:', errorMsg);
          } else {
            setIngestionStatus('success');
            setIngestionMessage('Finalization started in background');
          }
        })
        .catch((finalizeError: any) => {
          setIngestionStatus('error');
          const errorMsg = finalizeError?.response?.data?.detail || finalizeError?.message || 'Unknown error';
          setIngestionMessage(`Finalize failed: ${errorMsg}`);
          console.error('Finalize error:', finalizeError);
          console.log('Recording artifacts saved but not ingested to vector DB');
        });
      
      // Clear auto-stop timer if it exists
      if ((window as any).__recorderAutoStopTimeout) {
        clearTimeout((window as any).__recorderAutoStopTimeout);
        (window as any).__recorderAutoStopTimeout = null;
      }
      
      // Move to choice screen after waiting
      setTimeout(() => setCurrentStep('choice'), 1500);
    } catch (error: any) {
      console.error('Stop error:', error);
      alert(error?.message || 'Failed to stop recording');
    }
  };

  const handleChoiceSelect = (choice: 'manual' | 'automation') => {
    setSelectedPath(choice);
    if (choice === 'manual') {
      setTimeout(() => setCurrentStep('manual-test'), 500);
    } else {
      // Auto-populate test keyword from session name for automation path
      setTestKeyword(sessionName || activeSessionId || 'recorded-flow');
      setTimeout(() => setCurrentStep('automation-repo-input'), 500);
    }
  };

  const handleGenerateManual = async () => {
    if (!activeSessionId) {
      alert('No recording session found');
      return;
    }

    try {
      setGeneratingTestCases(true);
      
      // Create story from session metadata
      const story = `Generate manual test cases for recorded flow: ${sessionName || activeSessionId}`;
      
      let result;
      if (templateFile) {
        // Generate with template
        result = await generateTestCasesWithTemplate(story, false, templateFile);
      } else {
        // Generate without template
        result = await generateTestCases({
          story,
          llmOnly: false,
          asExcel: true
        });
      }
      
      setTestCaseResults(result);
      setGeneratingTestCases(false);
      setCurrentStep('manual-success');
    } catch (error: any) {
      console.error('Test case generation error:', error);
      setGeneratingTestCases(false);
      alert(error?.response?.data?.detail || error?.message || 'Failed to generate test cases');
    }
  };

  const handleTemplateUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
        setTemplateFile(file);
      } else {
        alert('Please upload an Excel file (.xlsx or .xls)');
      }
    }
  };

  const handleContinueFromManual = () => {
    // Mark manual path as completed
    setCompletedPaths(prev => new Set(prev).add('manual'));
    
    // If automation flow was already completed, skip the choice and go directly to completion
    if (completedPaths.has('automation')) {
      console.log('[Manual] Automation already done, going directly to completion');
      setCurrentStep('completion');
    } else {
      // Show the choice screen
      setCurrentStep('manual-next-choice');
    }
  };

  const handleManualNextChoice = (choice: 'complete' | 'automation') => {
    if (choice === 'complete') {
      setCurrentStep('completion');
    } else {
      // Auto-populate test keyword from session name
      setTestKeyword(sessionName || activeSessionId || 'recorded-flow');
      setCurrentStep('automation-repo-input');
    }
  };

  const handleRepoSubmit = async () => {
    if (!repoUrl || !testKeyword) {
      alert('Please provide repository URL');
      return;
    }
    
    setCurrentStep('automation-checking');
    
    try {
      // Step 1: Clone repository to framework_repos/ and search for keyword
      console.log('[Automation] Cloning repository and searching for keyword:', testKeyword);
      console.log('[Automation] Repository URL:', repoUrl);
      
      const data = await keywordInspect(testKeyword, repoUrl);
      console.log('[Automation] keywordInspect result:', data);
      console.log('[Automation] Messages from backend:', data.messages);
      console.log('[Automation] Full data:', JSON.stringify(data, null, 2));
      
      // Extract existing assets (test scripts found in the cloned framework)
      const existingAssets = data.existingAssets || [];
      console.log('[Automation] Found', existingAssets.length, 'existing assets');
      console.log('[Automation] existingAssets:', existingAssets);
      
      const testScripts = existingAssets.filter((asset: any) => asset.isTest);
      console.log('[Automation] Found', testScripts.length, 'test scripts with keyword');
      console.log('[Automation] testScripts:', testScripts);
      
      // Store refined recorder flow if available
      if (data.refinedRecorderFlow && data.refinedRecorderFlow.steps?.length > 0) {
        console.log('[Automation] Found refined recorder flow with', data.refinedRecorderFlow.steps.length, 'steps');
        setRefinedFlowSteps(data.refinedRecorderFlow.steps);
      } else {
        console.log('[Automation] No refined recorder flow found');
        setRefinedFlowSteps([]);
      }
      
      setExistingScripts(testScripts);
      
      setTimeout(() => setCurrentStep('automation-script-choice'), 1500);
    } catch (error: any) {
      console.error('Error checking repository:', error);
      console.error('Error details:', error.response?.data || error.message);
      alert(`Failed to check repository: ${error.response?.data?.detail || error.message}`);
      // Don't block the user - proceed with empty scripts
      setExistingScripts([]);
      setRefinedFlowSteps([]);
      setTimeout(() => setCurrentStep('automation-script-choice'), 1500);
    }
  };

  const handleScriptChoice = async (choice: 'existing' | 'refined') => {
    setSelectedScriptType(choice);
    if (choice === 'existing') {
      setCurrentStep('automation-existing-preview');
    } else {
      // Generate preview using agentic /agentic/preview endpoint
      try {
        setStreamingPreview(true);
        const scenario = testKeyword || sessionName || activeSessionId || 'test scenario';
        
        // Call agentic preview endpoint
        const preview = await previewAgentic(scenario);
        setEditableFlowPreview(preview);
        setCurrentStep('automation-refined-preview');
        
      } catch (error) {
        console.error('Error generating preview with agentic API:', error);
        
        // Fallback: try to load from refined flows or metadata
        if (activeSessionId) {
          try {
            const response = await fetch(`${API_BASE_URL}/api/recordings/refined-flows?recording_id=${activeSessionId}`);
            
            if (response.ok) {
              const data = await response.json();
              const flows = data.flows || [];
              const steps = flows.length > 0 ? flows[0].steps || [] : [];
              setRefinedFlowSteps(steps);
              
              if (steps.length > 0) {
                const preview = steps.map((step: any, idx: number) => {
                  const action = step.action || step.type || 'ACTION';
                  const target = step.selector || step.url || step.text || '';
                  const value = step.value || '';
                  const targetValue = value ? `${target} | '${value}'` : target;
                  return `step ${idx + 1} | ${action} | ${targetValue}`;
                }).join('\n');
                setEditableFlowPreview(preview);
              } else {
                setEditableFlowPreview(`No refined steps found.\nYou can manually add test steps here before generating the automation script.\n\nFormat: step 1 | action | target | 'value'`);
              }
            } else {
              await loadFromMetadata();
            }
          } catch (fallbackError) {
            console.error('Fallback also failed:', fallbackError);
            await loadFromMetadata();
          }
        }
        setCurrentStep('automation-refined-preview');
      } finally {
        setStreamingPreview(false);
      }
    }
  };

  // Helper function to load from metadata as fallback
  const loadFromMetadata = async () => {
    try {
      const metadataUrl = buildArtifactUrl(activeSessionId!, 'metadata.json');
      const metadataResponse = await fetch(metadataUrl);
      if (metadataResponse.ok) {
        const metadata = await metadataResponse.json();
        const actions = metadata.actions || [];
        setRefinedFlowSteps(actions);
        
        const preview = actions.map((action: any, idx: number) => {
          const actionType = action.type || 'ACTION';
          const target = action.selector || action.url || '';
          const value = action.value || '';
          const targetValue = value ? `${target} | '${value}'` : target;
          return `step ${idx + 1} | ${actionType} | ${targetValue}`;
        }).join('\n');
        setEditableFlowPreview(preview || `Session: ${sessionName || activeSessionId}\nMetadata loaded - ready for automation`);
      } else {
        throw new Error('Metadata not found');
      }
    } catch (error) {
      console.error('Metadata fallback failed:', error);
      setEditableFlowPreview(`Session: ${sessionName || activeSessionId}\n\nTest steps preview not available.\nYou can manually describe the test steps here:\n\nstep 1 | navigate | https://example.com\nstep 2 | click | button#login\nstep 3 | type | input[name="username"] | 'testuser'\nstep 4 | click | button[type="submit"]`);
      setRefinedFlowSteps([]);
    }
  };

  const handleGenerateScript = async () => {
    if (!activeSessionId && !editableFlowPreview) {
      alert('No flow preview available');
      return;
    }
    
    try {
      setStreamingPayload(true);
      setPayloadProgress('Initializing script generation...');
      
      const scenario = testKeyword || sessionName || activeSessionId || 'test scenario';
      
      // Use generatePayload API (non-streaming) for reliable script generation
      console.log('Calling generatePayload with scenario:', scenario);
      const data = await generatePayload(scenario, editableFlowPreview);
      console.log('Received payload data:', data);
      
      // Combine all generated files
      const allFiles = [
        ...(data.locators || []),
        ...(data.pages || []),
        ...(data.tests || [])
      ];
      
      // Store payload files for persist
      setPayloadFiles(allFiles);
      
      console.log('All files:', allFiles);
      
      // Find the test file
      const testFile = allFiles.find((f: any) => 
        f.path.startsWith('tests/') || 
        f.path.endsWith('.spec.ts') || 
        f.path.endsWith('.test.ts')
      );
      
      if (testFile) {
        console.log('Found test file:', testFile.path);
        setGeneratedScript(testFile.content);
      } else if (allFiles.length > 0) {
        console.log('No test file found, combining all files');
        const combinedScript = allFiles.map((f: any) => 
          `// File: ${f.path}\n\n${f.content}`
        ).join('\n\n// ==========================================\n\n');
        setGeneratedScript(combinedScript);
      } else {
        console.log('No files in payload, generating mock script');
        const mockScript = generateMockScript();
        setGeneratedScript(mockScript);
      }
      
      setPayloadProgress('Script generation complete!');
      setCurrentStep('automation-generated-script');
      
    } catch (error: any) {
      console.error('Error generating script:', error);
      setPayloadProgress(`Error: ${error.message}`);
      
      // Fallback: show mock script
      const mockScript = generateMockScript();
      setGeneratedScript(mockScript);
      setCurrentStep('automation-generated-script');
    } finally {
      setStreamingPayload(false);
    }
  };

  // Helper function to generate mock Playwright script for testing
  const generateMockScript = () => {
    const flowName = sessionName || activeSessionId || 'test';
    return `import { test, expect } from '@playwright/test';

// Generated from recording: ${flowName}
// Edited flow preview:
${editableFlowPreview.split('\n').map(line => '// ' + line).join('\n')}

test('${flowName}', async ({ page }) => {
  // This is a mock script for UI testing
  // The actual script will be generated by the backend API
  
${refinedFlowSteps.map((step: any, idx: number) => {
  const action = step.action || step.type || 'action';
  const selector = step.selector || 'selector';
  
  if (action.toLowerCase().includes('navigate') || action.toLowerCase().includes('goto')) {
    return `  // Step ${idx + 1}: Navigate\n  await page.goto('${step.url || 'https://example.com'}');`;
  } else if (action.toLowerCase().includes('click')) {
    return `  // Step ${idx + 1}: Click\n  await page.locator('${selector}').click();`;
  } else if (action.toLowerCase().includes('type') || action.toLowerCase().includes('fill')) {
    return `  // Step ${idx + 1}: Fill input\n  await page.locator('${selector}').fill('${step.value || 'test'}');`;
  } else {
    return `  // Step ${idx + 1}: ${action}\n  await page.locator('${selector}').click();`;
  }
}).join('\n\n')}
  
  // Add assertions as needed
  await expect(page).toHaveURL(/.*/);
});
`;
  };

  const handleContinueToTestManager = async () => {
    // Navigate to testmanager form and load existing data
    try {
      const frameworkRoot = repoUrl || undefined;
      
      // If using existing script, populate payloadFiles with a reference to it
      if (selectedScriptType === 'existing' && existingScripts.length > 0) {
        // Create a payload entry for the existing script
        // The backend will use the path to find the actual file during trial run
        setPayloadFiles([{
          path: existingScripts[0].path,
          content: '', // Will be loaded from repo during trial run
          isExisting: true
        }]);
      }
      
      // Load existing test case IDs from testmanager.xlsx
      const testManagerResponse = await fetch(
        `${API_BASE_URL}/config/list_test_manager${frameworkRoot ? `?frameworkRoot=${encodeURIComponent(frameworkRoot)}` : ''}`
      );
      
      if (testManagerResponse.ok) {
        const testManagerData = await testManagerResponse.json();
        const rows = testManagerData.rows || [];
        const ids = rows.map((r: any) => r.TestCaseID).filter(Boolean);
        setAvailableTestCaseIds(ids);
      }
      
      // Load available datasheets
      const datasheets = await listDatasheets(frameworkRoot);
      setAvailableDatasheets(datasheets);
      
      // Pre-populate fields
      setTestCaseDescription(testKeyword || sessionName || activeSessionId || '');
    } catch (error) {
      console.error('Error loading testmanager data:', error);
      setAvailableTestCaseIds([]);
      setAvailableDatasheets([]);
    }
    
    setCurrentStep('automation-testmanager-upload');
  };
  
  const handlePersistFiles = async () => {
    if (!testCaseId) {
      setPersistError('Please provide Test Case ID');
      return;
    }
    
    try {
      setPersisting(true);
      setPersistSuccess(null);
      setPersistError(null);
      const frameworkRoot = repoUrl || undefined;
      
      // Step 1: Upload new datasheet if provided
      let finalDatasheetName = datasheetName;
      if (datasheetFile) {
        const uploadResult = await uploadDatasheet(
          datasheetFile,
          testCaseId,
          frameworkRoot
        );
        console.log('Datasheet uploaded:', uploadResult);
        finalDatasheetName = uploadResult.filename || datasheetFile.name;
        setDatasheetName(finalDatasheetName);
      }
      
      // Step 2: Update testmanager.xlsx
      const updateResponse = await fetch(`${API_BASE_URL}/config/update_test_manager`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: testCaseId,
          datasheet: finalDatasheetName || '',
          referenceId: referenceId || '',
          idName: idName || '',
          frameworkRoot: frameworkRoot,
          newDescription: testCaseDescription,
          execute: executeValue,
          allowFreeformCreate: true
        })
      });
      
      if (!updateResponse.ok) {
        throw new Error(`Failed to update testmanager: ${updateResponse.status}`);
      }
      
      const updateResult = await updateResponse.json();
      console.log('TestManager updated:', updateResult);
      
      // Step 3: Persist the generated files to the repository (only if we have new files)
      // Skip persistence for existing scripts (isExisting flag)
      let writtenFiles = [];
      const hasNewFiles = payloadFiles.length > 0 && !payloadFiles[0]?.isExisting;
      
      if (hasNewFiles) {
        writtenFiles = await persistFiles(payloadFiles, '', frameworkRoot);
        console.log('Files persisted:', writtenFiles);
      } else if (payloadFiles[0]?.isExisting) {
        console.log('Using existing script, skipping file persistence to avoid overwriting');
      } else {
        console.log('No new files to persist');
      }
      
      const message = hasNewFiles
        ? `Successfully updated testmanager.xlsx and persisted ${writtenFiles.length} files to repository`
        : 'Successfully updated testmanager.xlsx (using existing test script)';
      
      setPersistSuccess({
        filesCount: writtenFiles.length,
        message
      });
      
      // Proceed to trial run after a brief delay to show success message
      setTimeout(() => {
        setCurrentStep('automation-trial-run');
      }, 2000);
    } catch (error: any) {
      console.error('Error in persist workflow:', error);
      setPersistError(error.message || 'Failed to persist files');
    } finally {
      setPersisting(false);
    }
  };

  const handleTrialRun = async () => {
    console.log('[TrialRun] Starting trial run, payloadFiles:', payloadFiles);
    console.log('[TrialRun] payloadFiles.length:', payloadFiles.length);
    console.log('[TrialRun] payloadFiles[0]:', payloadFiles[0]);
    console.log('[TrialRun] payloadFiles[0]?.isExisting:', payloadFiles[0]?.isExisting);
    console.log('[TrialRun] payloadFiles[0]?.content length:', payloadFiles[0]?.content?.length || 0);
    console.log('[TrialRun] selectedScriptType:', selectedScriptType);
    
    if (payloadFiles.length === 0) {
      console.error('[TrialRun] No payload files available');
      alert('No test files available to run. Please generate the automation script first.');
      return;
    }
    
    setTrialRunning(true);
    setTrialLogs('Initializing trial run...\n');
    setCurrentStep('automation-trial-run');
    
    try {
      const frameworkRoot = repoUrl || undefined;
      
      // Check if we're using an existing script
      const isExistingScript = payloadFiles[0]?.isExisting === true;
      
      console.log('[TrialRun] isExistingScript check:', isExistingScript);
      console.log('[TrialRun] Path to use:', isExistingScript ? 'trial-run-existing' : 'trial-run-stream');
      
      if (isExistingScript) {
        // For existing scripts, use the trial-run-existing endpoint
        console.log('[TrialRun] ✅ USING EXISTING SCRIPT ENDPOINT at path:', payloadFiles[0].path);
        
        const response = await fetch(`${API_BASE_URL}/agentic/trial-run-existing`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            testFilePath: payloadFiles[0].path,
            frameworkRoot: frameworkRoot,
            headed: true,
            scenario: testCaseId || testKeyword || sessionName || '',
            updateTestManager: true
          })
        });
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
          throw new Error(errorData.detail || `Trial run failed: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('[TrialRun] Trial run result:', result);
        
        setTrialLogs(result.logs || 'Trial run completed');
        setTrialResult({
          success: result.success,
          message: result.success ? 'Trial run completed successfully!' : 'Trial run failed',
          logs: result.logs || ''
        });
        setTrialRunning(false);
        return;
      }
      
      // For newly generated scripts, continue with existing logic
      const testFile = payloadFiles.find((f: any) => 
        f.path.startsWith('tests/') || 
        f.path.endsWith('.spec.ts') || 
        f.path.endsWith('.test.ts')
      );
      
      console.log('[TrialRun] ⚠️ USING STREAMING ENDPOINT (not existing script)');
      console.log('[TrialRun] Found test file:', testFile);
      console.log('[TrialRun] testFile.isExisting:', testFile?.isExisting);
      console.log('[TrialRun] testFile.content length:', testFile?.content?.length || 0);
      
      if (!testFile) {
        throw new Error('No test file found in generated payload');
      }
      
      console.log('[TrialRun] Running test file:', testFile.path);
      console.log('[TrialRun] Headed mode: true');
      console.log('[TrialRun] Framework root:', frameworkRoot);
      console.log('[TrialRun] Test file content preview:', testFile.content.substring(0, 500));
      
      // Basic validation: check for common syntax issues
      const syntaxIssues: string[] = [];
      if (testFile.content.includes('await ') && testFile.content.includes('.\d+\.')) {
        syntaxIssues.push('Detected potential numeric property accessor (e.g., .13.click())');
      }
      
      if (syntaxIssues.length > 0) {
        const warning = `⚠️ Potential syntax issues detected:\n${syntaxIssues.join('\n')}\n\nProceeding with trial run anyway...\n\n`;
        setTrialLogs(prev => prev + warning);
      }
      
      // Use streaming trial run for real-time logs
      await trialRunAgenticStream(
        testFile.content,
        true, // headed mode - show browser
        frameworkRoot,
        '', // token
        (event: any) => {
          console.log('[TrialRun] Event:', event);
          const phase = event.phase || event.type;
          
          if (phase === 'chunk' || phase === 'log' || phase === 'progress') {
            const message = event.data || event.message || '';
            setTrialLogs(prev => prev + message + '\n');
          } else if (phase === 'done' || phase === 'complete') {
            const success = event.success !== false;
            setTrialResult({
              success: success,
              message: success ? 'Trial run completed successfully!' : 'Trial run failed',
              logs: event.logs || ''
            });
            setTrialRunning(false);
          } else if (phase === 'error') {
            const errorMsg = event.error || event.message || 'Unknown error';
            setTrialLogs(prev => prev + `ERROR: ${errorMsg}\n`);
            setTrialResult({
              success: false,
              message: errorMsg,
              logs: event.logs || ''
            });
            setTrialRunning(false);
          } else if (phase === 'prepared') {
            // Show command being run
            const cmd = event.cmd || '';
            const cwd = event.cwd || '';
            setTrialLogs(prev => prev + `Command: ${cmd}\nWorking directory: ${cwd}\nHeaded mode: ${event.headed}\n\n`);
          } else if (phase === 'running') {
            setTrialLogs(prev => prev + 'Playwright test execution started...\n');
          }
        },
        undefined, // signal
        {
          scenario: testCaseId || testCaseDescription,
          datasheet: datasheetName,
          referenceId: referenceId,
          idName: idName,
          update: true // Update testmanager with results
        }
      );
      
    } catch (error: any) {
      console.error('[TrialRun] Trial run error:', error);
      setTrialLogs(prev => prev + `\nFATAL ERROR: ${error.message}\n`);
      setTrialResult({
        success: false,
        message: error?.message || 'Trial run failed',
        logs: error?.stack || 'No error logs available'
      });
      setTrialRunning(false);
    }
  };

  const handleGitPush = async () => {
    if (!repoUrl) {
      alert('Repository URL is required');
      return;
    }
    
    if (!gitBranch || !gitCommitMessage) {
      alert('Please provide branch name and commit message');
      return;
    }
    
    setGitPushing(true);
    setGitPushResult(null);
    
    try {
      const result = await pushToGit({
        repoUrl: repoUrl,
        branch: gitBranch,
        commitMessage: gitCommitMessage
      });
      
      setGitPushResult(result);
    } catch (error: any) {
      setGitPushResult({
        success: false,
        message: error?.message || 'Failed to push to git'
      });
    } finally {
      setGitPushing(false);
    }
  };

  const handleEditTestCaseId = (testCaseId: string) => {
    setEditingTestCaseId(testCaseId);
    setEditedTestCaseIdValue(testCaseId);
    setRenameResult(null);
  };

  const handleCancelEditTestCaseId = () => {
    setEditingTestCaseId(null);
    setEditedTestCaseIdValue('');
    setRenameResult(null);
  };

  const handleSaveTestCaseId = async () => {
    if (!editingTestCaseId || !editedTestCaseIdValue) {
      return;
    }
    
    if (editingTestCaseId === editedTestCaseIdValue) {
      // No change
      setEditingTestCaseId(null);
      return;
    }
    
    setRenamingTestCaseId(true);
    setRenameResult(null);
    
    try {
      const result = await renameTestCaseId(editingTestCaseId, editedTestCaseIdValue, repoUrl);
      setRenameResult(result);
      
      if (result.success) {
        // Update the available test case IDs list
        setAvailableTestCaseIds(prev => 
          prev.map(id => id === editingTestCaseId ? editedTestCaseIdValue : id)
        );
        // Update the selected test case ID if it was the one being edited
        if (testCaseId === editingTestCaseId) {
          setTestCaseId(editedTestCaseIdValue);
        }
        // Close the edit mode after a short delay
        setTimeout(() => {
          setEditingTestCaseId(null);
          setEditedTestCaseIdValue('');
        }, 1500);
      }
    } catch (error: any) {
      setRenameResult({
        success: false,
        message: error?.message || 'Failed to rename TestCaseID'
      });
    } finally {
      setRenamingTestCaseId(false);
    }
  };

  const handleGoBack = () => {
    // Navigate backward based on current step
    const backMap: Record<FlowStep, FlowStep> = {
      'home': 'home',
      'recorder-start': 'home',
      'recorder-active': 'recorder-start',
      'choice': 'recorder-active',
      'manual-test': 'choice',
      'manual-success': 'manual-test',
      'manual-next-choice': 'manual-success',
      'automation-repo-input': selectedPath === 'automation' ? 'choice' : 'manual-next-choice',
      'automation-checking': 'automation-repo-input',
      'automation-script-choice': 'automation-checking',
      'automation-existing-preview': 'automation-script-choice',
      'automation-refined-preview': 'automation-script-choice',
      'automation-generated-script': 'automation-refined-preview',
      'automation-testmanager-upload': selectedScriptType === 'existing' ? 'automation-existing-preview' : 'automation-generated-script',
      'automation-trial-run': 'automation-testmanager-upload',
      'completion': currentStep
    };
    
    const prevStep = backMap[currentStep];
    if (prevStep && prevStep !== currentStep) {
      setCurrentStep(prevStep);
    }
  };

  const handleReturnHome = () => {
    // Reset all state
    setCurrentStep('home');
    setSelectedPath(null);
    setCompletedPaths(new Set()); // Reset completed paths
    setSessionName('');
    setUrl('');
    setActiveSessionId(null);
    setTemplateFile(null);
    setTestCaseResults(null);
    setRepoUrl('');
    setTestKeyword('');
    setExistingScripts([]);
    setSelectedScriptType(null);
    setGeneratedScript('');
    setTestManagerFile(null);
    setTrialResult(null);
    setCodeExpanded(false);
    setFullCodeContent('');
  };

  const slideVariants = {
    enter: (direction: number) => ({
      x: direction > 0 ? '100%' : '-100%',
      opacity: 0,
      scale: 0.8,
    }),
    center: {
      x: 0,
      opacity: 1,
      scale: 1,
    },
    exit: (direction: number) => ({
      x: direction > 0 ? '-100%' : '100%',
      opacity: 0,
      scale: 0.8,
    }),
  };

  return (
    <div className="relative min-h-screen bg-black overflow-hidden">
      {/* 3D Particle Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div 
          className="absolute inset-0 bg-gradient-to-br from-purple-950/30 via-slate-950/50 to-blue-950/30"
          style={{
            transform: `translate(${mousePosition.x * 20}px, ${mousePosition.y * 20}px)`,
            transition: 'transform 0.3s ease-out'
          }}
        />
        {[...Array(150)].map((_, i) => {
          const depth = Math.random();
          const size = 1 + depth * 4;
          const x = Math.random() * 100;
          const y = Math.random() * 100;
          const isBlue = depth > 0.5;
          return (
            <motion.div
              key={i}
              className="absolute rounded-full"
              style={{
                left: `${x}%`,
                top: `${y}%`,
                width: `${size}px`,
                height: `${size}px`,
                background: `radial-gradient(circle, ${isBlue ? 'rgba(168, 85, 247, 0.6)' : 'rgba(59, 130, 246, 0.4)'} 0%, transparent 70%)`,
                filter: 'blur(1px)',
                transform: `translateX(${mousePosition.x * depth * 40}px) translateY(${mousePosition.y * depth * 40}px)`,
                boxShadow: isBlue 
                  ? '0 0 20px rgba(168, 85, 247, 0.3)' 
                  : '0 0 15px rgba(59, 130, 246, 0.2)',
              }}
              animate={{
                y: [0, -30 * depth, 0],
                opacity: [0.4, 0.8, 0.4],
                scale: [1, 1 + depth * 0.3, 1],
              }}
              transition={{
                duration: 5 + Math.random() * 4,
                repeat: Infinity,
                delay: Math.random() * 3,
                ease: 'easeInOut',
              }}
            />
          );
        })}
      </div>

      {/* Back Button */}
      {currentStep !== 'home' && (
        <motion.button
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          onClick={handleReturnHome}
          className="fixed top-8 left-8 z-50 flex items-center gap-2 px-6 py-3 bg-white/10 backdrop-blur-md border border-white/20 rounded-xl text-white hover:bg-white/20 transition-all duration-300"
        >
          <ArrowLeft size={20} />
          <span>Home</span>
        </motion.button>
      )}

      {/* Main Content - Horizontal Scrolling Container */}
      <div className="relative z-10 min-h-screen flex items-center justify-center">
        <AnimatePresence mode="wait">
          {/* HOME SCREEN */}
          {currentStep === 'home' && (
            <motion.div
              key="home"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              {/* Admin Button - Top Right */}
              <motion.button
                initial={{ opacity: 0, x: 50 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.5 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setCurrentStep('admin-home')}
                className="fixed top-8 right-8 px-6 py-3 bg-gradient-to-r from-amber-600 to-orange-600 rounded-xl text-white font-semibold shadow-2xl shadow-amber-500/30 hover:shadow-amber-400/50 transition-all flex items-center gap-2 z-50"
              >
                <Settings size={20} />
                Admin
              </motion.button>
              
              <div className="container mx-auto">
                <motion.div
                  initial={{ opacity: 0, y: -80 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 1.2, delay: 0.3 }}
                  className="text-center mb-24"
                >
                  <h1 className="text-8xl font-bold mb-8 bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 bg-clip-text text-transparent">
                    ESAN
                  </h1>
                  <p className="text-3xl text-gray-300 font-light">Test Script Automation Studio </p>
                </motion.div>

                <div className="grid md:grid-cols-2 gap-16 max-w-6xl mx-auto">
                  {/* Design Card */}
                  <ChoiceCard
                    icon={<Lightbulb size={100} />}
                    title="DESIGN"
                    subtitle="Create tests"
                    color="blue"
                    onClick={handleDesignClick}
                    delay={0.6}
                  />

                  {/* Execute Card */}
                  <ChoiceCard
                    icon={<Play size={100} fill="currentColor" />}
                    title="EXECUTE"
                    subtitle="Run suites"
                    color="purple"
                    onClick={handleExecuteClick}
                    delay={0.8}
                  />
                </div>
              </div>
            </motion.div>
          )}

          {/* ADMIN HOME SCREEN */}
          {currentStep === 'admin-home' && (
            <motion.div
              key="admin-home"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="container mx-auto">
                <motion.div
                  initial={{ opacity: 0, y: -80 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 1.2, delay: 0.3 }}
                  className="text-center mb-24"
                >
                  <h1 className="text-8xl font-bold mb-8 bg-gradient-to-r from-amber-400 via-orange-500 to-red-500 bg-clip-text text-transparent">
                    Admin Panel
                  </h1>
                  <p className="text-3xl text-gray-300 font-light">Manage data sources and vector database</p>
                </motion.div>

                <div className="grid md:grid-cols-2 gap-12 max-w-6xl mx-auto">
                  {/* Jira Ingestion */}
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.5, type: 'spring', stiffness: 100 }}
                    whileHover={{ scale: 1.05, y: -10 }}
                    onClick={() => setCurrentStep('admin-jira')}
                    className="cursor-pointer"
                  >
                    <div className="h-64 bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-8 text-center hover:border-blue-400/60 transition-all shadow-2xl hover:shadow-blue-500/30">
                      <motion.div
                        animate={{ rotate: [0, 5, -5, 0] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <Database size={80} className="mx-auto text-blue-400 mb-4" />
                      </motion.div>
                      <h3 className="text-3xl font-bold text-white mb-2">Jira Ingestion</h3>
                      <p className="text-lg text-blue-200">Import test cases from Jira</p>
                    </div>
                  </motion.div>

                  {/* Website Ingestion */}
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.6, type: 'spring', stiffness: 100 }}
                    whileHover={{ scale: 1.05, y: -10 }}
                    onClick={() => setCurrentStep('admin-website')}
                    className="cursor-pointer"
                  >
                    <div className="h-64 bg-gradient-to-br from-green-900/40 to-green-600/20 backdrop-blur-xl border-2 border-green-500/30 rounded-3xl p-8 text-center hover:border-green-400/60 transition-all shadow-2xl hover:shadow-green-500/30">
                      <motion.div
                        animate={{ scale: [1, 1.1, 1] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <Globe size={80} className="mx-auto text-green-400 mb-4" />
                      </motion.div>
                      <h3 className="text-3xl font-bold text-white mb-2">Website Ingestion</h3>
                      <p className="text-lg text-green-200">Crawl and index web content</p>
                    </div>
                  </motion.div>

                  {/* Document Ingestion */}
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.7, type: 'spring', stiffness: 100 }}
                    whileHover={{ scale: 1.05, y: -10 }}
                    onClick={() => setCurrentStep('admin-documents')}
                    className="cursor-pointer"
                  >
                    <div className="h-64 bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-8 text-center hover:border-purple-400/60 transition-all shadow-2xl hover:shadow-purple-500/30">
                      <motion.div
                        animate={{ y: [0, -10, 0] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <BookOpen size={80} className="mx-auto text-purple-400 mb-4" />
                      </motion.div>
                      <h3 className="text-3xl font-bold text-white mb-2">Document Ingestion</h3>
                      <p className="text-lg text-purple-200">Upload PDFs, Docs, and files</p>
                    </div>
                  </motion.div>

                  {/* Vector Management */}
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.8, type: 'spring', stiffness: 100 }}
                    whileHover={{ scale: 1.05, y: -10 }}
                    onClick={() => setCurrentStep('admin-vector')}
                    className="cursor-pointer"
                  >
                    <div className="h-64 bg-gradient-to-br from-orange-900/40 to-orange-600/20 backdrop-blur-xl border-2 border-orange-500/30 rounded-3xl p-8 text-center hover:border-orange-400/60 transition-all shadow-2xl hover:shadow-orange-500/30">
                      <motion.div
                        animate={{ rotate: [0, 360] }}
                        transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
                      >
                        <FileSearch size={80} className="mx-auto text-orange-400 mb-4" />
                      </motion.div>
                      <h3 className="text-3xl font-bold text-white mb-2">Vector Management</h3>
                      <p className="text-lg text-orange-200">Query and manage vector DB</p>
                    </div>
                  </motion.div>
                </div>

                {/* Back Button */}
                <div className="mt-16 text-center">
                  <motion.button
                    whileHover={{ x: -5 }}
                    onClick={() => setCurrentStep('home')}
                    className="px-8 py-4 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto text-lg"
                  >
                    <ArrowLeft size={24} />
                    Back to Home
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* ADMIN JIRA INGESTION SCREEN */}
          {currentStep === 'admin-jira' && (
            <motion.div
              key="admin-jira"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <motion.div
                  initial={{ opacity: 0, y: -50 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center mb-12"
                >
                  <Database size={80} className="mx-auto text-blue-400 mb-6" />
                  <h2 className="text-6xl font-bold mb-4 bg-gradient-to-r from-blue-400 to-blue-600 bg-clip-text text-transparent">
                    Jira Ingestion
                  </h2>
                  <p className="text-2xl text-gray-300">Import test cases from Jira using JQL</p>
                </motion.div>

                <div className="bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12">
                  <div className="space-y-6 mb-8">
                    <div>
                      <label className="text-blue-200 mb-3 text-lg font-medium block">
                        JQL Query
                      </label>
                      <textarea
                        value={jiraJql}
                        onChange={(e) => setJiraJql(e.target.value)}
                        placeholder='project = "TEST" AND type = "Test Case"'
                        rows={4}
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg placeholder-gray-400 focus:outline-none focus:border-blue-400 transition-all resize-none"
                      />
                      <p className="mt-2 text-sm text-blue-300">Enter a valid Jira JQL query to fetch test cases</p>
                    </div>
                  </div>

                  {adminSuccess && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-green-500/20 border border-green-500/50 rounded-xl text-green-200"
                    >
                      {adminSuccess}
                    </motion.div>
                  )}

                  {adminError && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-200"
                    >
                      {adminError}
                    </motion.div>
                  )}

                  <div className="flex gap-4">
                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={async () => {
                        setAdminLoading(true);
                        setAdminSuccess(null);
                        setAdminError(null);
                        try {
                          const result = await ingestJira(jiraJql);
                          setAdminSuccess(`Successfully ingested ${result.count || 0} Jira items`);
                          setJiraJql('');
                        } catch (error: any) {
                          setAdminError(error.message || 'Failed to ingest Jira data');
                        } finally {
                          setAdminLoading(false);
                        }
                      }}
                      disabled={!jiraJql || adminLoading}
                      className="flex-1 py-6 bg-gradient-to-r from-blue-600 to-blue-500 rounded-2xl text-white text-2xl font-semibold shadow-2xl disabled:opacity-50"
                    >
                      {adminLoading ? 'Ingesting...' : 'Ingest from Jira'}
                    </motion.button>

                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={() => setCurrentStep('admin-home')}
                      className="px-8 py-6 bg-white/5 border border-white/10 rounded-2xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2"
                    >
                      <ArrowLeft size={24} />
                      Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* ADMIN WEBSITE INGESTION SCREEN */}
          {currentStep === 'admin-website' && (
            <motion.div
              key="admin-website"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <motion.div
                  initial={{ opacity: 0, y: -50 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center mb-12"
                >
                  <Globe size={80} className="mx-auto text-green-400 mb-6" />
                  <h2 className="text-6xl font-bold mb-4 bg-gradient-to-r from-green-400 to-green-600 bg-clip-text text-transparent">
                    Website Ingestion
                  </h2>
                  <p className="text-2xl text-gray-300">Crawl and index web content</p>
                </motion.div>

                <div className="bg-gradient-to-br from-green-900/40 to-green-600/20 backdrop-blur-xl border-2 border-green-500/30 rounded-3xl p-12">
                  <div className="space-y-6 mb-8">
                    <div>
                      <label className="text-green-200 mb-3 text-lg font-medium block">
                        Website URL
                      </label>
                      <input
                        type="url"
                        value={websiteUrl}
                        onChange={(e) => setWebsiteUrl(e.target.value)}
                        placeholder="https://example.com/docs"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg placeholder-gray-400 focus:outline-none focus:border-green-400 transition-all"
                      />
                    </div>

                    <div>
                      <label className="text-green-200 mb-3 text-lg font-medium block">
                        Max Crawl Depth
                      </label>
                      <input
                        type="number"
                        value={websiteMaxDepth}
                        onChange={(e) => setWebsiteMaxDepth(parseInt(e.target.value) || 3)}
                        min="1"
                        max="10"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg focus:outline-none focus:border-green-400 transition-all"
                      />
                      <p className="mt-2 text-sm text-green-300">How many levels deep to crawl (1-10)</p>
                    </div>
                  </div>

                  {adminSuccess && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-green-500/20 border border-green-500/50 rounded-xl text-green-200"
                    >
                      {adminSuccess}
                    </motion.div>
                  )}

                  {adminError && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-200"
                    >
                      {adminError}
                    </motion.div>
                  )}

                  <div className="flex gap-4">
                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={async () => {
                        setAdminLoading(true);
                        setAdminSuccess(null);
                        setAdminError(null);
                        try {
                          const result = await ingestWebsite({ url: websiteUrl, maxDepth: websiteMaxDepth });
                          setAdminSuccess(`Successfully crawled and ingested website (Job ID: ${result.jobId})`);
                          setWebsiteUrl('');
                        } catch (error: any) {
                          setAdminError(error.message || 'Failed to crawl website');
                        } finally {
                          setAdminLoading(false);
                        }
                      }}
                      disabled={!websiteUrl || adminLoading}
                      className="flex-1 py-6 bg-gradient-to-r from-green-600 to-green-500 rounded-2xl text-white text-2xl font-semibold shadow-2xl disabled:opacity-50"
                    >
                      {adminLoading ? 'Crawling...' : 'Crawl Website'}
                    </motion.button>

                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={() => setCurrentStep('admin-home')}
                      className="px-8 py-6 bg-white/5 border border-white/10 rounded-2xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2"
                    >
                      <ArrowLeft size={24} />
                      Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* ADMIN DOCUMENT INGESTION SCREEN */}
          {currentStep === 'admin-documents' && (
            <motion.div
              key="admin-documents"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <motion.div
                  initial={{ opacity: 0, y: -50 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center mb-12"
                >
                  <BookOpen size={80} className="mx-auto text-purple-400 mb-6" />
                  <h2 className="text-6xl font-bold mb-4 bg-gradient-to-r from-purple-400 to-purple-600 bg-clip-text text-transparent">
                    Document Ingestion
                  </h2>
                  <p className="text-2xl text-gray-300">Upload PDFs, Docs, and files</p>
                </motion.div>

                <div className="bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12">
                  <div className="space-y-6 mb-8">
                    <div>
                      <label className="text-purple-200 mb-3 text-lg font-medium block">
                        Select Files
                      </label>
                      <input
                        ref={documentInputRef}
                        type="file"
                        multiple
                        accept=".pdf,.doc,.docx,.txt,.md"
                        onChange={(e) => {
                          const files = Array.from(e.target.files || []);
                          setDocumentFiles(files);
                        }}
                        className="hidden"
                      />
                      <div
                        onClick={() => documentInputRef.current?.click()}
                        className="w-full px-6 py-12 bg-white/10 backdrop-blur-md border-2 border-dashed border-purple-400/50 rounded-xl text-center cursor-pointer hover:bg-white/20 hover:border-purple-400 transition-all"
                      >
                        <BookOpen size={48} className="mx-auto text-purple-400 mb-4" />
                        <p className="text-white text-lg mb-2">
                          {documentFiles.length > 0 
                            ? `${documentFiles.length} file(s) selected` 
                            : 'Click to select files or drag & drop'}
                        </p>
                        <p className="text-sm text-purple-300">PDF, DOC, DOCX, TXT, MD</p>
                      </div>
                      
                      {documentFiles.length > 0 && (
                        <div className="mt-4 space-y-2">
                          {documentFiles.map((file, idx) => (
                            <div key={idx} className="flex items-center justify-between px-4 py-2 bg-white/5 rounded-lg">
                              <span className="text-white">{file.name}</span>
                              <span className="text-purple-300 text-sm">{(file.size / 1024).toFixed(1)} KB</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {adminSuccess && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-green-500/20 border border-green-500/50 rounded-xl text-green-200"
                    >
                      {adminSuccess}
                    </motion.div>
                  )}

                  {adminError && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-200"
                    >
                      {adminError}
                    </motion.div>
                  )}

                  <div className="flex gap-4">
                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={async () => {
                        setAdminLoading(true);
                        setAdminSuccess(null);
                        setAdminError(null);
                        try {
                          const result = await ingestDocuments(documentFiles);
                          setAdminSuccess(`Successfully ingested ${result.count || documentFiles.length} document(s)`);
                          setDocumentFiles([]);
                          if (documentInputRef.current) documentInputRef.current.value = '';
                        } catch (error: any) {
                          setAdminError(error.message || 'Failed to ingest documents');
                        } finally {
                          setAdminLoading(false);
                        }
                      }}
                      disabled={documentFiles.length === 0 || adminLoading}
                      className="flex-1 py-6 bg-gradient-to-r from-purple-600 to-purple-500 rounded-2xl text-white text-2xl font-semibold shadow-2xl disabled:opacity-50"
                    >
                      {adminLoading ? 'Uploading...' : 'Upload Documents'}
                    </motion.button>

                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={() => setCurrentStep('admin-home')}
                      className="px-8 py-6 bg-white/5 border border-white/10 rounded-2xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2"
                    >
                      <ArrowLeft size={24} />
                      Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* ADMIN VECTOR MANAGEMENT SCREEN */}
          {currentStep === 'admin-vector' && (
            <motion.div
              key="admin-vector"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-6xl mx-auto">
                <motion.div
                  initial={{ opacity: 0, y: -50 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center mb-12"
                >
                  <FileSearch size={80} className="mx-auto text-orange-400 mb-6" />
                  <h2 className="text-6xl font-bold mb-4 bg-gradient-to-r from-orange-400 to-orange-600 bg-clip-text text-transparent">
                    Vector Database
                  </h2>
                  <p className="text-2xl text-gray-300">Manage and query indexed content</p>
                </motion.div>

                <div className="bg-gradient-to-br from-orange-900/40 to-orange-600/20 backdrop-blur-xl border-2 border-orange-500/30 rounded-3xl p-8">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-2xl font-bold text-white">Indexed Documents ({vectorDocs.length})</h3>
                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={async () => {
                        setAdminLoading(true);
                        try {
                          const result = await queryVectorAll(1000);
                          setVectorDocs(result.results || []);
                          setSelectedDocIds(new Set()); // Clear selection on refresh
                          setCurrentPage(1); // Reset to first page
                        } catch (error: any) {
                          setAdminError(error.message || 'Failed to load vector documents');
                        } finally {
                          setAdminLoading(false);
                        }
                      }}
                      className="px-6 py-3 bg-orange-600 rounded-xl text-white font-semibold hover:bg-orange-500 transition-all"
                    >
                      {adminLoading ? 'Loading...' : 'Refresh'}
                    </motion.button>
                  </div>

                  {/* Delete by Source Section */}
                  <div className="mb-6 p-6 bg-white/5 rounded-2xl border border-white/10">
                    <h4 className="text-lg font-semibold text-white mb-4">Bulk Delete by Source</h4>
                    <div className="flex flex-wrap gap-3">
                      {['jira', 'website', 'documents', 'refined_recorder'].map((source) => {
                        const count = vectorDocs.filter(doc => doc.metadata?.source === source).length;
                        return (
                          <motion.button
                            key={source}
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={async () => {
                              if (confirm(`Delete all ${count} documents from source "${source}"?`)) {
                                setAdminLoading(true);
                                setAdminSuccess(null);
                                setAdminError(null);
                                try {
                                  await deleteVectorSource(source);
                                  setAdminSuccess(`Deleted all documents from source: ${source}`);
                                  // Refresh the list
                                  const result = await queryVectorAll(1000);
                                  setVectorDocs(result.results || []);
                                  setSelectedDocIds(new Set()); // Clear selection
                                  setCurrentPage(1); // Reset to first page
                                } catch (error: any) {
                                  setAdminError(error.message || `Failed to delete source: ${source}`);
                                } finally {
                                  setAdminLoading(false);
                                }
                              }
                            }}
                            disabled={count === 0 || adminLoading}
                            className={`px-4 py-2 rounded-lg font-semibold transition-all ${
                              count === 0 
                                ? 'bg-gray-700 text-gray-500 cursor-not-allowed' 
                                : 'bg-red-600/80 text-white hover:bg-red-500'
                            }`}
                          >
                            {source} ({count})
                          </motion.button>
                        );
                      })}
                    </div>
                  </div>

                  {adminSuccess && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-green-500/20 border border-green-500/50 rounded-xl text-green-200"
                    >
                      {adminSuccess}
                    </motion.div>
                  )}

                  {adminError && (
                    <motion.div
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-200"
                    >
                      {adminError}
                    </motion.div>
                  )}

                  {/* Selection Actions */}
                  {vectorDocs.length > 0 && (() => {
                    const totalPages = Math.ceil(vectorDocs.length / itemsPerPage);
                    const startIndex = (currentPage - 1) * itemsPerPage;
                    const endIndex = startIndex + itemsPerPage;
                    const currentPageDocs = vectorDocs.slice(startIndex, endIndex);
                    const allCurrentPageSelected = currentPageDocs.length > 0 && currentPageDocs.every(d => selectedDocIds.has(d.id));
                    
                    return (
                      <>
                        <div className="mb-4 flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/10">
                          <div className="flex items-center gap-4">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={allCurrentPageSelected}
                                onChange={(e) => {
                                  const newSelected = new Set(selectedDocIds);
                                  if (e.target.checked) {
                                    currentPageDocs.forEach(d => newSelected.add(d.id));
                                  } else {
                                    currentPageDocs.forEach(d => newSelected.delete(d.id));
                                  }
                                  setSelectedDocIds(newSelected);
                                }}
                                className="w-4 h-4 rounded border-2 border-orange-400 bg-white/10 checked:bg-orange-500 cursor-pointer"
                              />
                              <span className="text-white font-medium">Select All on Page ({currentPageDocs.length})</span>
                            </label>
                            <span className="text-orange-300">
                              {selectedDocIds.size} selected
                            </span>
                          </div>
                      
                      {selectedDocIds.size > 0 && (
                        <motion.button
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={{ opacity: 1, scale: 1 }}
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={async () => {
                            if (confirm(`Delete ${selectedDocIds.size} selected document(s)?`)) {
                              console.log('[VectorMgmt] Deleting selected documents:', Array.from(selectedDocIds));
                              setAdminLoading(true);
                              setAdminSuccess(null);
                              setAdminError(null);
                              try {
                                const deletePromises = Array.from(selectedDocIds).map(id => {
                                  console.log('[VectorMgmt] Deleting:', id);
                                  return deleteVectorDoc(id);
                                });
                                const results = await Promise.all(deletePromises);
                                console.log('[VectorMgmt] Delete results:', results);
                                setAdminSuccess(`Deleted ${selectedDocIds.size} document(s)`);
                                setVectorDocs(prev => prev.filter(d => !selectedDocIds.has(d.id)));
                                setSelectedDocIds(new Set());
                              } catch (error: any) {
                                console.error('[VectorMgmt] Delete error:', error);
                                setAdminError(error.message || 'Failed to delete selected documents');
                              } finally {
                                setAdminLoading(false);
                              }
                            }
                          }}
                          className="px-6 py-2 bg-red-600 rounded-xl text-white font-semibold hover:bg-red-500 transition-all flex items-center gap-2"
                        >
                          <span>Delete Selected ({selectedDocIds.size})</span>
                        </motion.button>
                      )}
                    </div>

                    <div className="overflow-x-auto max-h-96 overflow-y-auto">
                      <table className="w-full text-white">
                        <thead className="bg-white/10 sticky top-0">
                          <tr>
                            <th className="px-4 py-3 text-center w-12"></th>
                            <th className="px-4 py-3 text-left">ID</th>
                            <th className="px-4 py-3 text-left">Content Preview</th>
                            <th className="px-4 py-3 text-left">Source</th>
                            <th className="px-4 py-3 text-center">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {vectorDocs.length === 0 ? (
                            <tr>
                              <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                                No documents found. Click Refresh to load.
                              </td>
                            </tr>
                          ) : (
                            currentPageDocs.map((doc) => (
                            <tr key={doc.id} className="border-b border-white/10 hover:bg-white/5">
                              <td className="px-4 py-3 text-center">
                                <input
                                  type="checkbox"
                                  checked={selectedDocIds.has(doc.id)}
                                  onChange={(e) => {
                                    const newSelected = new Set(selectedDocIds);
                                    if (e.target.checked) {
                                      newSelected.add(doc.id);
                                    } else {
                                      newSelected.delete(doc.id);
                                    }
                                    setSelectedDocIds(newSelected);
                                  }}
                                  className="w-4 h-4 rounded border-2 border-orange-400 bg-white/10 checked:bg-orange-500 cursor-pointer"
                                />
                              </td>
                              <td className="px-4 py-3 font-mono text-sm text-orange-300">{doc.id}</td>
                              <td className="px-4 py-3 max-w-md truncate">{doc.content?.substring(0, 100)}...</td>
                              <td className="px-4 py-3 text-sm text-gray-300">{doc.metadata?.source || 'N/A'}</td>
                              <td className="px-4 py-3 text-center">
                                <motion.button
                                  whileHover={{ scale: 1.1 }}
                                  onClick={async () => {
                                    if (confirm(`Delete document ${doc.id}?`)) {
                                      console.log('[VectorMgmt] Deleting document:', doc.id);
                                      setAdminLoading(true);
                                      try {
                                        const result = await deleteVectorDoc(doc.id);
                                        console.log('[VectorMgmt] Delete result:', result);
                                        setAdminSuccess(`Deleted document ${doc.id}`);
                                        setVectorDocs(prev => prev.filter(d => d.id !== doc.id));
                                        setSelectedDocIds(prev => {
                                          const newSet = new Set(prev);
                                          newSet.delete(doc.id);
                                          return newSet;
                                        });
                                      } catch (error: any) {
                                        console.error('[VectorMgmt] Delete error:', error);
                                        setAdminError(error.message || 'Failed to delete');
                                      } finally {
                                        setAdminLoading(false);
                                      }
                                    }
                                  }}
                                  className="px-3 py-1 bg-red-600/80 rounded text-sm hover:bg-red-500"
                                >
                                  Delete
                                </motion.button>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                  </>
                    );
                  })()}

                  {/* Pagination Controls */}
                  {vectorDocs.length > 0 && (() => {
                    const totalPages = Math.ceil(vectorDocs.length / itemsPerPage);
                    const startIndex = (currentPage - 1) * itemsPerPage;
                    const endIndex = startIndex + itemsPerPage;
                    
                    return (
                      <div className="mt-6 flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <label className="text-white font-medium">Items per page:</label>
                          <select
                            value={itemsPerPage}
                            onChange={(e) => {
                              setItemsPerPage(Number(e.target.value));
                              setCurrentPage(1);
                            }}
                            className="px-4 py-2 bg-white/10 border-2 border-white/20 rounded-xl text-white focus:outline-none focus:border-orange-400"
                          >
                            <option value={25}>25</option>
                            <option value={50}>50</option>
                            <option value={100}>100</option>
                            <option value={200}>200</option>
                          </select>
                          <span className="text-gray-300">
                            Showing {startIndex + 1}-{Math.min(endIndex, vectorDocs.length)} of {vectorDocs.length}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={() => setCurrentPage(1)}
                            disabled={currentPage === 1}
                            className="px-4 py-2 bg-white/10 rounded-lg text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition-all"
                          >
                            First
                          </motion.button>
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage === 1}
                            className="px-4 py-2 bg-white/10 rounded-lg text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition-all"
                          >
                            Previous
                          </motion.button>
                          
                          <div className="flex items-center gap-2">
                            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                              let pageNum;
                              if (totalPages <= 5) {
                                pageNum = i + 1;
                              } else if (currentPage <= 3) {
                                pageNum = i + 1;
                              } else if (currentPage >= totalPages - 2) {
                                pageNum = totalPages - 4 + i;
                              } else {
                                pageNum = currentPage - 2 + i;
                              }
                              
                              return (
                                <motion.button
                                  key={pageNum}
                                  whileHover={{ scale: 1.05 }}
                                  whileTap={{ scale: 0.95 }}
                                  onClick={() => setCurrentPage(pageNum)}
                                  className={`px-4 py-2 rounded-lg transition-all ${
                                    currentPage === pageNum
                                      ? 'bg-orange-600 text-white font-bold'
                                      : 'bg-white/10 text-white hover:bg-white/20'
                                  }`}
                                >
                                  {pageNum}
                                </motion.button>
                              );
                            })}
                          </div>

                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                            className="px-4 py-2 bg-white/10 rounded-lg text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition-all"
                          >
                            Next
                          </motion.button>
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={() => setCurrentPage(totalPages)}
                            disabled={currentPage === totalPages}
                            className="px-4 py-2 bg-white/10 rounded-lg text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/20 transition-all"
                          >
                            Last
                          </motion.button>
                        </div>
                      </div>
                    );
                  })()}

                  <div className="mt-8 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={() => setCurrentStep('admin-home')}
                      className="px-8 py-4 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={24} />
                      Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* RECORDER START SCREEN */}
          {currentStep === 'recorder-start' && (
            <motion.div
              key="recorder-start"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <h2 className="text-6xl font-bold mb-16 text-center text-white">Start Recording</h2>
                
                <div className="bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12">
                  <div className="space-y-6 mb-12">
                    {/* URL Input */}
                    <div>
                      <label className="flex items-center gap-2 text-blue-200 mb-3 text-lg font-medium">
                        <Globe size={20} />
                        Target URL
                      </label>
                      <input
                        type="url"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="https://example.com"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg placeholder-gray-400 focus:outline-none focus:border-blue-400 transition-all"
                      />
                    </div>

                    {/* Session Name Input */}
                    <div>
                      <label className="flex items-center gap-2 text-blue-200 mb-3 text-lg font-medium">
                        <FileText size={20} />
                        Flow Name (Session)
                      </label>
                      <input
                        type="text"
                        value={sessionName}
                        onChange={(e) => setSessionName(e.target.value)}
                        placeholder="login-flow"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg placeholder-gray-400 focus:outline-none focus:border-blue-400 transition-all"
                      />
                    </div>

                    {/* Timer Input */}
                    <div>
                      <label className="flex items-center gap-2 text-blue-200 mb-3 text-lg font-medium">
                        <Clock size={20} />
                        Timer (seconds)
                      </label>
                      <input
                        type="number"
                        value={timer}
                        onChange={(e) => setTimer(e.target.value)}
                        placeholder="60"
                        min="10"
                        max="600"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white text-lg placeholder-gray-400 focus:outline-none focus:border-blue-400 transition-all"
                      />
                    </div>
                  </div>

                  {/* Start Recording Button */}
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handleStartRecording}
                    disabled={!sessionName || !url}
                    className="w-full py-6 bg-gradient-to-r from-red-600 to-pink-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-red-500/50 hover:shadow-red-400/70 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
                  >
                    <Circle size={32} className="fill-current" />
                    Start Recording
                  </motion.button>
                  
                  <p className="mt-6 text-center text-blue-300 text-sm">
                    Playwright will launch Chromium browser for recording
                  </p>
                </div>
              </div>
            </motion.div>
          )}

          {/* RECORDER ACTIVE SCREEN */}
          {currentStep === 'recorder-active' && (
            <motion.div
              key="recorder-active"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-4xl mx-auto">
                <div className="text-center mb-12">
                  <RecordButton onClick={() => {}} isRecording={true} />
                  <h3 className="mt-8 text-white text-3xl font-bold">{recordingStatus || 'Recording in progress...'}</h3>
                  <p className="mt-4 text-gray-300 text-lg">Chromium browser is open - interact with it to record your flow</p>
                  
                  {activeSessionId && (
                    <div className="mt-6">
                      <p className="text-blue-400 text-sm mb-4">Session: {activeSessionId}</p>
                      <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={handleStopRecording}
                        className="px-8 py-3 bg-red-600/80 hover:bg-red-600 rounded-xl text-white font-semibold transition-all"
                      >
                        Stop Recording
                      </motion.button>
                    </div>
                  )}
                </div>

                {/* Live Event Feed */}
                {eventMessages.length > 0 && (
                  <div className="bg-gradient-to-br from-slate-900/60 to-slate-800/40 backdrop-blur-xl border border-white/10 rounded-2xl p-6 max-h-96 overflow-y-auto">
                    <h4 className="text-white text-lg font-semibold mb-4 flex items-center gap-2">
                      <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                      Live Events
                    </h4>
                    <div className="space-y-2">
                      {eventMessages.slice(-10).reverse().map((msg, idx) => (
                        <motion.div
                          key={idx}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="text-sm text-gray-300 bg-black/20 px-4 py-2 rounded-lg"
                        >
                          {msg}
                        </motion.div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* EXECUTE CHOICE SCREEN - Dropdown selection for existing flows */}
          {currentStep === 'execute-choice' && (
            <ExecuteFlow
              onComplete={handleReturnHome}
              onSelectManual={handleExecuteManualSelect}
              onSelectAutomation={handleExecuteAutomationSelect}
            />
          )}

          {/* CHOICE SCREEN */}
          {currentStep === 'choice' && (
            <motion.div
              key="choice"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="container mx-auto">
                <h2 className="text-6xl font-bold mb-8 text-center text-white">Choose Your Next Step</h2>
                
                {/* Ingestion Status Banner */}
                {ingestionStatus && (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className={`max-w-3xl mx-auto mb-12 p-6 rounded-2xl border-2 shadow-2xl ${
                      ingestionStatus === 'success' 
                        ? 'bg-gradient-to-r from-green-900/40 to-emerald-800/40 border-green-500/60' 
                        : ingestionStatus === 'error'
                        ? 'bg-gradient-to-r from-red-900/40 to-orange-800/40 border-red-500/60'
                        : 'bg-gradient-to-r from-blue-900/40 to-indigo-800/40 border-blue-500/60'
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 mt-1">
                        {ingestionStatus === 'pending' && (
                          <Loader2 size={32} className="animate-spin text-blue-400" />
                        )}
                        {ingestionStatus === 'success' && (
                          <div className="relative">
                            <CheckCircle2 size={32} className="text-green-400" />
                            <div className="absolute inset-0 animate-ping opacity-75">
                              <CheckCircle2 size={32} className="text-green-400" />
                            </div>
                          </div>
                        )}
                        {ingestionStatus === 'error' && (
                          <span className="text-3xl">⚠️</span>
                        )}
                      </div>
                      <div className="flex-1">
                        <h3 className={`text-xl font-bold mb-2 ${
                          ingestionStatus === 'success' ? 'text-green-100' : 
                          ingestionStatus === 'error' ? 'text-red-100' : 'text-blue-100'
                        }`}>
                          {ingestionStatus === 'success' && '✨ Recording Successfully Saved!'}
                          {ingestionStatus === 'pending' && '🔄 Processing Recording...'}
                          {ingestionStatus === 'error' && '⚠️ Processing Issue'}
                        </h3>
                        <p className={`text-base ${
                          ingestionStatus === 'success' ? 'text-green-200' : 
                          ingestionStatus === 'error' ? 'text-red-200' : 'text-blue-200'
                        }`}>
                          {ingestionMessage}
                        </p>
                        {ingestionStatus === 'success' && (
                          <p className="mt-3 text-sm text-green-300 bg-green-950/30 px-4 py-2 rounded-lg border border-green-500/30">
                            💡 Your flow has been refined and ingested into the vector database. 
                            <span className="font-semibold"> Ready to generate test cases!</span>
                          </p>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
                
                <div className="grid md:grid-cols-2 gap-16 max-w-5xl mx-auto">
                  <PathCard
                    icon={<FileText size={80} />}
                    title="Manual Test Cases"
                    description="Create detailed documentation"
                    color="blue"
                    isSelected={selectedPath === 'manual'}
                    onClick={() => handleChoiceSelect('manual')}
                  />
                  
                  <PathCard
                    icon={<Code2 size={80} />}
                    title="Automation Scripts"
                    description="Build automated test scripts"
                    color="purple"
                    isSelected={selectedPath === 'automation'}
                    onClick={() => handleChoiceSelect('automation')}
                  />
                </div>
              </div>
            </motion.div>
          )}

          {/* MANUAL TEST GENERATION */}
          {currentStep === 'manual-test' && (
            <motion.div
              key="manual-test"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Generate Manual Test Cases</h2>
                
                <div className="bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12">
                  <div className="mb-8">
                    <p className="text-xl text-blue-200 mb-2">Flow: <span className="text-white font-semibold">{sessionName || activeSessionId}</span></p>
                    <p className="text-sm text-blue-300/70">Generate structured test cases from your recorded flow</p>
                  </div>

                  {/* Template Upload Section */}
                  <div className="mb-8 p-6 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl">
                    <label className="block text-blue-200 mb-3 text-lg font-semibold flex items-center gap-2">
                      <FileText size={20} />
                      Upload Excel Template (Optional)
                    </label>
                    <p className="text-sm text-blue-300/70 mb-4">
                      Provide an Excel template to structure your test cases. If not provided, default format will be used.
                    </p>
                    
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".xlsx,.xls"
                      onChange={handleTemplateUpload}
                      className="hidden"
                    />
                    
                    <div className="flex items-center gap-4">
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => fileInputRef.current?.click()}
                        className="px-6 py-3 bg-white/10 border-2 border-white/20 rounded-xl text-white font-semibold hover:bg-white/20 transition-all"
                      >
                        Choose File
                      </motion.button>
                      {templateFile && (
                        <div className="flex items-center gap-2 text-green-300">
                          <CheckCircle2 size={20} />
                          <span className="text-sm">{templateFile.name}</span>
                          <button
                            onClick={() => setTemplateFile(null)}
                            className="ml-2 text-red-400 hover:text-red-300"
                          >
                            ✕
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handleGenerateManual}
                    disabled={generatingTestCases}
                    className="w-full py-6 bg-gradient-to-r from-blue-600 to-cyan-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-blue-500/50 hover:shadow-blue-400/70 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
                  >
                    {generatingTestCases ? (
                      <>
                        <Loader2 size={28} className="animate-spin" />
                        Generating Test Cases...
                      </>
                    ) : (
                      <>
                        <FileText size={28} />
                        Generate Test Cases
                      </>
                    )}
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* MANUAL SUCCESS */}
          {currentStep === 'manual-success' && (
            <motion.div
              key="manual-success"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Test Cases Generated!</h2>
                
                <div className="bg-gradient-to-br from-green-900/40 to-emerald-600/20 backdrop-blur-xl border-2 border-green-500/30 rounded-3xl p-12 text-center">
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: 'spring', stiffness: 200, delay: 0.2 }}
                  >
                    <CheckCircle2 size={100} className="mx-auto text-green-400 mb-8" />
                  </motion.div>
                  
                  <h3 className="text-4xl font-bold text-white mb-4">Success!</h3>
                  <p className="text-xl text-green-200 mb-8">
                    Generated {testCaseResults?.records?.length || 0} test case(s) for <span className="font-semibold">{sessionName || activeSessionId}</span>
                  </p>
                  
                  {/* Preview Test Cases */}
                  {testCaseResults?.records && testCaseResults.records.length > 0 && (
                    <div className="mb-8 p-6 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl text-left max-h-64 overflow-y-auto">
                      <h4 className="text-lg font-semibold text-green-300 mb-4">Test Case Preview:</h4>
                      <div className="space-y-3 text-sm text-white/80">
                        {testCaseResults.records.slice(0, 3).map((record: any, idx: number) => (
                          <div key={idx} className="p-3 bg-white/5 rounded-lg">
                            <p className="font-semibold text-white">Test Case #{idx + 1}</p>
                            {Object.entries(record).slice(0, 3).map(([key, value]) => (
                              <p key={key} className="text-xs">
                                <span className="text-green-300">{key}:</span> {String(value).substring(0, 100)}
                              </p>
                            ))}
                          </div>
                        ))}
                        {testCaseResults.records.length > 3 && (
                          <p className="text-center text-green-300/70">...and {testCaseResults.records.length - 3} more</p>
                        )}
                      </div>
                    </div>
                  )}
                  
                  <div className="flex gap-6 justify-center">
                    {testCaseResults?.excel && (
                      <motion.a
                        href={`data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,${testCaseResults.excel}`}
                        download={`test-cases-${sessionName || activeSessionId}.xlsx`}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className="px-8 py-4 bg-green-600 rounded-xl text-white text-lg font-semibold flex items-center gap-2 hover:bg-green-500 transition-all"
                      >
                        <FileText size={20} />
                        Download Excel
                      </motion.a>
                    )}
                    <motion.button
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                      onClick={handleContinueFromManual}
                      className="px-8 py-4 bg-gradient-to-r from-green-600 to-emerald-600 rounded-xl text-white text-lg font-semibold hover:from-green-500 hover:to-emerald-500 transition-all shadow-lg"
                    >
                      Next Steps →
                    </motion.button>
                  </div>
                  
                  {/* Session Artifacts */}
                  {activeSessionId && sessionArtifacts?.artifacts && (
                    <div className="mt-8 pt-6 border-t border-white/10">
                      <h4 className="text-xl font-semibold text-white mb-4">Recording Artifacts</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {sessionArtifacts.artifacts.latestScreenshot && (
                          <div className="bg-white/5 rounded-lg p-4">
                            <p className="text-sm text-green-300 mb-2 font-semibold">Latest Screenshot</p>
                            <a 
                              href={buildArtifactUrl(activeSessionId, sessionArtifacts.artifacts.latestScreenshot)} 
                              target="_blank" 
                              rel="noreferrer"
                              className="block"
                            >
                              <img 
                                src={buildArtifactUrl(activeSessionId, sessionArtifacts.artifacts.latestScreenshot)} 
                                alt="Latest screenshot" 
                                className="w-full rounded border border-white/20 hover:border-green-400/50 transition-all"
                              />
                            </a>
                          </div>
                        )}
                        <div className="bg-white/5 rounded-lg p-4">
                          <p className="text-sm text-green-300 mb-3 font-semibold">Downloads</p>
                          <div className="space-y-2 text-sm">
                            {sessionArtifacts.artifacts.trace && (
                              <a 
                                href={buildArtifactUrl(activeSessionId, sessionArtifacts.artifacts.trace)} 
                                target="_blank" 
                                rel="noreferrer"
                                className="block text-blue-300 hover:text-blue-200 underline"
                              >
                                📦 trace.zip - Playwright Trace
                              </a>
                            )}
                            {sessionArtifacts.artifacts.har && (
                              <a 
                                href={buildArtifactUrl(activeSessionId, sessionArtifacts.artifacts.har)} 
                                target="_blank" 
                                rel="noreferrer"
                                className="block text-blue-300 hover:text-blue-200 underline"
                              >
                                🌐 network.har - HTTP Archive
                              </a>
                            )}
                            {sessionArtifacts.artifacts.metadata && (
                              <a 
                                href={buildArtifactUrl(activeSessionId, sessionArtifacts.artifacts.metadata)} 
                                target="_blank" 
                                rel="noreferrer"
                                className="block text-blue-300 hover:text-blue-200 underline"
                              >
                                📄 metadata.json - Session Data
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}

          {/* MANUAL NEXT CHOICE */}
          {currentStep === 'manual-next-choice' && (
            <motion.div
              key="manual-next-choice"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-5xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">What's Next?</h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* Complete Task Card */}
                  <motion.button
                    whileHover={{ scale: 1.05, rotateY: 5 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleManualNextChoice('complete')}
                    className="relative group"
                  >
                    <div className="h-full bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12 text-center hover:border-blue-400/60 transition-all shadow-2xl hover:shadow-blue-500/30">
                      <motion.div
                        animate={{ scale: [1, 1.1, 1] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <CheckCircle2 size={80} className="mx-auto text-blue-400 mb-6" />
                      </motion.div>
                      <h3 className="text-3xl font-bold text-white mb-4">Complete Task</h3>
                      <p className="text-lg text-blue-200">
                        Finish here and return to home
                      </p>
                    </div>
                  </motion.button>

                  {/* Generate Automation Script Card */}
                  <motion.button
                    whileHover={{ scale: 1.05, rotateY: -5 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleManualNextChoice('automation')}
                    className="relative group"
                  >
                    <div className="h-full bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12 text-center hover:border-purple-400/60 transition-all shadow-2xl hover:shadow-purple-500/30">
                      <motion.div
                        animate={{ rotate: [0, 10, -10, 0] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <Code2 size={80} className="mx-auto text-purple-400 mb-6" />
                      </motion.div>
                      <h3 className="text-3xl font-bold text-white mb-4">Generate Automation Script</h3>
                      <p className="text-lg text-purple-200">
                        Create executable test automation
                      </p>
                    </div>
                  </motion.button>
                </div>
                
                {/* Back Button */}
                <div className="mt-8 text-center">
                  <motion.button
                    whileHover={{ x: -5 }}
                    onClick={handleGoBack}
                    className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                  >
                    <ArrowLeft size={20} />
                    Go Back
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION REPO INPUT */}
          {currentStep === 'automation-repo-input' && (
            <motion.div
              key="automation-repo-input"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-3xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Repository Configuration</h2>
                
                <div className="bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12">
                  <div className="space-y-6 mb-8">
                    <div>
                      <label className="block text-purple-200 mb-2 text-lg flex items-center gap-2">
                        <Globe size={20} />
                        Repository URL:
                      </label>
                      <input
                        type="text"
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                        placeholder="https://github.com/mycompany/test-automation"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-purple-400 transition-all"
                      />
                    </div>
                    <div>
                      <label className="block text-purple-200 mb-2 text-lg flex items-center gap-2">
                        <Search size={20} />
                        Test Flow Keyword:
                      </label>
                      <input
                        type="text"
                        value={testKeyword}
                        onChange={(e) => setTestKeyword(e.target.value)}
                        placeholder="e.g., Create Supplier, Login Flow, Purchase Order"
                        className="w-full px-6 py-4 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-purple-400 transition-all"
                      />
                      {(sessionName || activeSessionId) && (
                        <p className="text-purple-300/60 text-sm mt-2 italic">
                          Auto-populated from recording: {sessionName || activeSessionId}
                        </p>
                      )}
                    </div>
                  </div>
                  
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handleRepoSubmit}
                    disabled={!repoUrl}
                    className="w-full py-6 bg-gradient-to-r from-purple-600 to-pink-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-purple-500/50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Check Repository →
                  </motion.button>
                  
                  {/* Back Button */}
                  <div className="mt-6 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={handleGoBack}
                      className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={20} />
                      Go Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION CHECKING */}
          {currentStep === 'automation-checking' && (
            <motion.div
              key="automation-checking"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-2xl mx-auto text-center">
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                  className="mb-8"
                >
                  <Loader2 size={100} className="mx-auto text-purple-400" />
                </motion.div>
                
                <h3 className="text-4xl font-bold text-white mb-6">Checking Repository...</h3>
                <div className="space-y-3 text-lg text-gray-300">
                  <p className="flex items-center justify-center gap-2">
                    <Globe size={20} className="text-blue-400" />
                    Cloning repository to framework_repos/
                  </p>
                  <p className="flex items-center justify-center gap-2">
                    <Search size={20} className="text-purple-400" />
                    Searching for tests containing: <span className="font-semibold text-purple-400">"{testKeyword}"</span>
                  </p>
                  <p className="flex items-center justify-center gap-2">
                    <FileSearch size={20} className="text-green-400" />
                    Checking vector DB for refined recorder flows
                  </p>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION SCRIPT CHOICE */}
          {currentStep === 'automation-script-choice' && (
            <motion.div
              key="automation-script-choice"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-5xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Choose Your Path</h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* Existing Script Card */}
                  <motion.button
                    whileHover={{ scale: 1.05, rotateY: 5 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleScriptChoice('existing')}
                    className="relative group"
                  >
                    <div className="h-full bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12 text-left hover:border-blue-400/60 transition-all shadow-2xl hover:shadow-blue-500/30">
                      <FileText size={80} className="text-blue-400 mb-6" />
                      <h3 className="text-3xl font-bold text-white mb-4">Use Existing Script</h3>
                      <p className="text-lg text-blue-200 mb-6">
                        Found {existingScripts.length} existing test script(s) in repository
                      </p>
                      {existingScripts.length > 0 && (
                        <div className="bg-white/5 rounded-lg p-4 text-sm">
                          <p className="text-blue-300 font-semibold mb-2">Latest script:</p>
                          <p className="text-white/80 truncate">{existingScripts[0]?.path || 'N/A'}</p>
                        </div>
                      )}
                    </div>
                  </motion.button>

                  {/* Refined Recorder Flow Card */}
                  <motion.button
                    whileHover={{ scale: 1.05, rotateY: -5 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => handleScriptChoice('refined')}
                    className="relative group"
                  >
                    <div className="h-full bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12 text-left hover:border-purple-400/60 transition-all shadow-2xl hover:shadow-purple-500/30">
                      <Circle size={80} className="text-purple-400 mb-6" />
                      <h3 className="text-3xl font-bold text-white mb-4">Use Refined Recorder Flow</h3>
                      <p className="text-lg text-purple-200 mb-6">
                        Generate new automation script from your recorded flow
                      </p>
                      <div className="bg-white/5 rounded-lg p-4 text-sm">
                        <p className="text-purple-300 font-semibold mb-2">Session:</p>
                        <p className="text-white/80 truncate">{sessionName || activeSessionId}</p>
                      </div>
                    </div>
                  </motion.button>
                </div>
                
                {/* Back Button */}
                <div className="mt-8 text-center">
                  <motion.button
                    whileHover={{ x: -5 }}
                    onClick={handleGoBack}
                    className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                  >
                    <ArrowLeft size={20} />
                    Go Back
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION EXISTING PREVIEW */}
          {currentStep === 'automation-existing-preview' && (
            <motion.div
              key="automation-existing-preview"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-4xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Existing Test Script</h2>
                
                <div className="bg-gradient-to-br from-blue-900/40 to-blue-600/20 backdrop-blur-xl border-2 border-blue-500/30 rounded-3xl p-12">
                  {existingScripts.length > 0 ? (
                    <>
                      <div className="mb-8">
                        <h4 className="text-2xl font-semibold text-white mb-4">Script Details</h4>
                        <div className="bg-white/5 rounded-lg p-6 space-y-3 text-white/80">
                          <p><span className="text-blue-300 font-semibold">Path:</span> {existingScripts[0].path}</p>
                          <p><span className="text-blue-300 font-semibold">Relevance:</span> {existingScripts[0].relevance || 0} keyword matches</p>
                        </div>
                      </div>
                      
                      <div className="mb-8">
                        <div className="flex items-center justify-between mb-4">
                          <h4 className="text-xl font-semibold text-white">Code Preview</h4>
                          <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={async () => {
                              if (!codeExpanded && !fullCodeContent) {
                                // Fetch full file content
                                setLoadingFullCode(true);
                                try {
                                  const frameworkRoot = repoUrl || undefined;
                                  const response = await fetch(
                                    `${API_BASE_URL}/agentic/read-file?filePath=${encodeURIComponent(existingScripts[0].path)}${frameworkRoot ? `&frameworkRoot=${encodeURIComponent(frameworkRoot)}` : ''}`
                                  );
                                  if (response.ok) {
                                    const data = await response.json();
                                    setFullCodeContent(data.content || existingScripts[0].snippet || '');
                                  } else {
                                    setFullCodeContent(existingScripts[0].snippet || '// Could not load full file');
                                  }
                                } catch (error) {
                                  console.error('Error loading full file:', error);
                                  setFullCodeContent(existingScripts[0].snippet || '// Error loading file');
                                } finally {
                                  setLoadingFullCode(false);
                                }
                              }
                              setCodeExpanded(!codeExpanded);
                            }}
                            className="px-4 py-2 bg-blue-600/30 hover:bg-blue-600/50 rounded-lg text-blue-200 text-sm flex items-center gap-2 transition-all border border-blue-500/30"
                          >
                            {loadingFullCode ? (
                              <>
                                <Loader2 size={16} className="animate-spin" />
                                Loading...
                              </>
                            ) : codeExpanded ? (
                              <>
                                <ChevronUp size={16} />
                                Collapse
                              </>
                            ) : (
                              <>
                                <ChevronDown size={16} />
                                Expand Full Code
                              </>
                            )}
                          </motion.button>
                        </div>
                        <div className={`bg-black/30 rounded-lg p-6 overflow-y-auto border border-blue-500/30 transition-all duration-300 ${
                          codeExpanded ? 'max-h-[600px]' : 'max-h-96'
                        }`}>
                          <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">
                            {codeExpanded && fullCodeContent 
                              ? fullCodeContent 
                              : existingScripts[0].snippet || '// No preview available'}
                          </pre>
                        </div>
                        {!codeExpanded && existingScripts[0].snippet && (
                          <p className="mt-2 text-sm text-blue-300/60 italic">
                            Showing snippet with keyword matches. Click "Expand Full Code" to view the complete file.
                          </p>
                        )}
                        {codeExpanded && (
                          <p className="mt-2 text-sm text-blue-300/60 italic">
                            Showing complete file content from repository.
                          </p>
                        )}
                      </div>
                      
                      {existingScripts.length > 1 && (
                        <div className="mb-8">
                          <h4 className="text-lg font-semibold text-white mb-3">
                            Other matching scripts ({existingScripts.length - 1})
                          </h4>
                          <div className="space-y-2">
                            {existingScripts.slice(1, 4).map((script, idx) => (
                              <div key={idx} className="bg-white/5 rounded-lg p-4 flex items-center justify-between">
                                <span className="text-white/80 font-mono text-sm">{script.path}</span>
                                <span className="text-blue-300 text-xs">{script.relevance} matches</span>
                              </div>
                            ))}
                            {existingScripts.length > 4 && (
                              <p className="text-white/50 text-sm text-center mt-2">
                                +{existingScripts.length - 4} more scripts
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                      
                      <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={handleContinueToTestManager}
                        className="w-full py-6 bg-gradient-to-r from-blue-600 to-cyan-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-blue-500/50"
                      >
                        Continue to Upload TestManager →
                      </motion.button>
                    </>
                  ) : (
                    <p className="text-center text-white/60 text-xl">No existing scripts found</p>
                  )}
                  
                  {/* Back Button */}
                  <div className="mt-6 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={handleGoBack}
                      className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={20} />
                      Go Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION REFINED PREVIEW */}
          {currentStep === 'automation-refined-preview' && (
            <motion.div
              key="automation-refined-preview"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-5xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Refined Flow Preview</h2>
                
                <div className="bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12">
                  {/* Session Info */}
                  <div className="mb-6 p-4 bg-white/5 rounded-xl border border-purple-400/30">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-purple-200 text-sm">Recording Session</p>
                        <p className="text-white text-lg font-semibold">{sessionName || activeSessionId}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-purple-200 text-sm">Total Steps</p>
                        <p className="text-white text-2xl font-bold">{refinedFlowSteps.length}</p>
                      </div>
                    </div>
                  </div>

                  {/* Editable Flow Preview */}
                  <div className="mb-8">
                    <div className="flex items-center justify-between mb-4">
                      <h4 className="text-xl font-semibold text-white">Editable Flow Preview</h4>
                      {streamingPreview ? (
                        <span className="text-purple-300 text-sm flex items-center gap-2">
                          <Loader2 size={16} className="animate-spin" />
                          Loading preview...
                        </span>
                      ) : (
                        <span className="text-purple-300 text-sm italic">✏️ You can edit before generating</span>
                      )}
                    </div>
                    <textarea
                      value={editableFlowPreview}
                      onChange={(e) => setEditableFlowPreview(e.target.value)}
                      disabled={streamingPreview}
                      className="w-full h-96 bg-black/30 rounded-lg p-6 text-sm text-purple-300 font-mono border-2 border-purple-400/30 focus:border-purple-400 focus:outline-none resize-none disabled:opacity-50"
                      placeholder="Flow steps will appear here for editing...\n\nFormat: step 1 | action | target | 'value'"
                    />
                    <p className="text-purple-300/60 text-sm mt-2">💡 Edit the steps above to customize the automation script generation</p>
                  </div>
                  
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handleGenerateScript}
                    disabled={streamingPayload}
                    className="w-full py-6 bg-gradient-to-r from-purple-600 to-pink-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-purple-500/50 flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {streamingPayload ? (
                      <>
                        <Loader2 size={28} className="animate-spin" />
                        {payloadProgress || 'Generating Script...'}
                      </>
                    ) : (
                      <>
                        <Code2 size={28} />
                        Generate Automation Script →
                      </>
                    )}
                  </motion.button>
                  
                  {/* Back Button */}
                  <div className="mt-6 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={handleGoBack}
                      className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={20} />
                      Go Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION GENERATED SCRIPT */}
          {currentStep === 'automation-generated-script' && (
            <motion.div
              key="automation-generated-script"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-4xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Generated Test Script</h2>
                
                <div className="bg-gradient-to-br from-green-900/40 to-emerald-600/20 backdrop-blur-xl border-2 border-green-500/30 rounded-3xl p-12">
                  <div className="mb-8">
                    <div className="flex items-center justify-between mb-4">
                      <h4 className="text-xl font-semibold text-white">Playwright TypeScript Code</h4>
                      <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className="px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm hover:bg-white/20 transition-all"
                      >
                        📋 Copy Code
                      </motion.button>
                    </div>
                    <div className="bg-black/30 rounded-lg p-6 max-h-96 overflow-y-auto">
                      <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">
                        {generatedScript || '// Generated script will appear here...'}
                      </pre>
                    </div>
                  </div>
                  
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handleContinueToTestManager}
                    className="w-full py-6 bg-gradient-to-r from-green-600 to-emerald-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-green-500/50"
                  >
                    Continue to Upload TestManager →
                  </motion.button>
                  
                  {/* Back Button */}
                  <div className="mt-6 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={handleGoBack}
                      className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={20} />
                      Go Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION TESTMANAGER UPLOAD */}
          {currentStep === 'automation-testmanager-upload' && (
            <motion.div
              key="automation-testmanager-upload"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-4xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">TestManager Configuration</h2>
                
                <div className="bg-gradient-to-br from-orange-900/40 to-amber-600/20 backdrop-blur-xl border-2 border-orange-500/30 rounded-3xl p-12">
                  <p className="text-orange-200 mb-8 text-center text-lg">
                    Configure TestManager details - this will update testmanager.xlsx in your framework repository
                  </p>
                  
                  {/* Test Case ID - Dropdown + Input + Edit */}
                  <div className="mb-6">
                    <label className="block text-orange-200 mb-2 text-lg font-semibold">
                      Test Case ID *
                    </label>
                    {!isNewTestCaseId ? (
                      <div className="space-y-3">
                        <div className="flex gap-3">
                          <select
                            value={testCaseId}
                            onChange={(e) => {
                              if (e.target.value === '__CREATE_NEW__') {
                                setIsNewTestCaseId(true);
                                setTestCaseId('');
                              } else {
                                setTestCaseId(e.target.value);
                              }
                            }}
                            className="flex-1 px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white focus:border-orange-400 focus:outline-none"
                          >
                            <option value="">Select existing Test Case ID...</option>
                            {availableTestCaseIds.map((id) => (
                              <option key={id} value={id}>{id}</option>
                            ))}
                            <option value="__CREATE_NEW__">➕ Create New Test Case ID</option>
                          </select>
                        </div>
                        
                        {/* Edit existing TestCaseID */}
                        {availableTestCaseIds.length > 0 && (
                          <div className="p-4 bg-black/20 border border-orange-400/20 rounded-lg">
                            <div className="flex items-center justify-between mb-3">
                              <span className="text-orange-200 text-sm font-semibold">Edit Existing Test Case IDs</span>
                            </div>
                            <div className="space-y-2 max-h-48 overflow-y-auto">
                              {availableTestCaseIds.map((id) => (
                                <div key={id} className="flex items-center gap-2 p-2 bg-white/5 rounded">
                                  {editingTestCaseId === id ? (
                                    <>
                                      <input
                                        type="text"
                                        value={editedTestCaseIdValue}
                                        onChange={(e) => setEditedTestCaseIdValue(e.target.value)}
                                        className="flex-1 px-3 py-2 bg-black/40 border border-orange-400/40 rounded text-white text-sm focus:outline-none focus:border-orange-400"
                                        disabled={renamingTestCaseId}
                                      />
                                      <motion.button
                                        whileHover={{ scale: 1.1 }}
                                        whileTap={{ scale: 0.9 }}
                                        onClick={handleSaveTestCaseId}
                                        disabled={renamingTestCaseId}
                                        className="p-2 bg-green-600 rounded text-white hover:bg-green-700 disabled:opacity-50"
                                        title="Save"
                                      >
                                        {renamingTestCaseId ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                                      </motion.button>
                                      <motion.button
                                        whileHover={{ scale: 1.1 }}
                                        whileTap={{ scale: 0.9 }}
                                        onClick={handleCancelEditTestCaseId}
                                        disabled={renamingTestCaseId}
                                        className="p-2 bg-red-600 rounded text-white hover:bg-red-700 disabled:opacity-50"
                                        title="Cancel"
                                      >
                                        <X size={16} />
                                      </motion.button>
                                    </>
                                  ) : (
                                    <>
                                      <span className="flex-1 text-white text-sm">{id}</span>
                                      <motion.button
                                        whileHover={{ scale: 1.1 }}
                                        whileTap={{ scale: 0.9 }}
                                        onClick={() => handleEditTestCaseId(id)}
                                        className="p-2 bg-orange-600 rounded text-white hover:bg-orange-700"
                                        title="Edit"
                                      >
                                        <Edit2 size={16} />
                                      </motion.button>
                                    </>
                                  )}
                                </div>
                              ))}
                            </div>
                            
                            {renameResult && (
                              <motion.div
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className={`mt-3 p-3 rounded border text-sm ${
                                  renameResult.success
                                    ? 'bg-green-900/40 border-green-500/60 text-green-200'
                                    : 'bg-red-900/40 border-red-500/60 text-red-200'
                                }`}
                              >
                                {renameResult.message}
                              </motion.div>
                            )}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="flex gap-3">
                        <input
                          type="text"
                          value={testCaseId}
                          onChange={(e) => setTestCaseId(e.target.value)}
                          placeholder="Enter new Test Case ID"
                          className="flex-1 px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white placeholder-white/40 focus:border-orange-400 focus:outline-none"
                        />
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={() => {
                            setIsNewTestCaseId(false);
                            setTestCaseId('');
                          }}
                          className="px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white hover:bg-white/20 transition-all"
                        >
                          ← Back to Select
                        </motion.button>
                      </div>
                    )}
                  </div>
                  
                  {/* Test Case Description */}
                  <div className="mb-6">
                    <label className="block text-orange-200 mb-2 text-lg font-semibold">
                      Test Case Description (Optional)
                    </label>
                    <input
                      type="text"
                      value={testCaseDescription}
                      onChange={(e) => setTestCaseDescription(e.target.value)}
                      placeholder="e.g., Create Supplier Flow, Login Validation"
                      className="w-full px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white placeholder-white/40 focus:border-orange-400 focus:outline-none"
                    />
                  </div>
                  
                  {/* Datasheet Name - Dropdown + Upload */}
                  <div className="mb-6">
                    <label className="block text-orange-200 mb-2 text-lg font-semibold">
                      Datasheet Name (Optional)
                    </label>
                    <select
                      value={datasheetName}
                      onChange={(e) => setDatasheetName(e.target.value)}
                      className="w-full px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white focus:border-orange-400 focus:outline-none mb-3"
                    >
                      <option value="">Select existing datasheet...</option>
                      {availableDatasheets.map((ds) => (
                        <option key={ds} value={ds}>{ds}</option>
                      ))}
                    </select>
                    
                    <div className="flex items-center gap-3">
                      <span className="text-orange-300/70 text-sm">Or upload new datasheet:</span>
                      <input
                        ref={datasheetInputRef}
                        type="file"
                        accept=".xlsx,.xls"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            setDatasheetFile(file);
                            setDatasheetName(file.name);
                          }
                        }}
                        className="hidden"
                      />
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => datasheetInputRef.current?.click()}
                        className="px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white text-sm hover:bg-white/15 hover:border-orange-400/50 transition-all flex items-center gap-2"
                      >
                        <Upload size={16} />
                        {datasheetFile ? datasheetFile.name : 'Upload New'}
                      </motion.button>
                    </div>
                  </div>
                  
                  {/* Execute Dropdown */}
                  <div className="mb-6">
                    <label className="block text-orange-200 mb-2 text-lg font-semibold">
                      Execute
                    </label>
                    <select
                      value={executeValue}
                      onChange={(e) => setExecuteValue(e.target.value)}
                      className="w-full px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white focus:border-orange-400 focus:outline-none"
                    >
                      <option value="Yes">Yes</option>
                      <option value="No">No</option>
                    </select>
                  </div>
                  
                  {/* Reference ID */}
                  <div className="mb-6">
                    <label className="block text-orange-200 mb-2 text-lg font-semibold">
                      Reference ID (Optional)
                    </label>
                    <input
                      type="text"
                      value={referenceId}
                      onChange={(e) => setReferenceId(e.target.value)}
                      placeholder="e.g., REF_001, JIRA-123"
                      className="w-full px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white placeholder-white/40 focus:border-orange-400 focus:outline-none"
                    />
                  </div>
                  
                  {/* ID Name */}
                  <div className="mb-8">
                    <label className="block text-orange-200 mb-2 text-lg font-semibold">
                      ID Name (Optional)
                    </label>
                    <input
                      type="text"
                      value={idName}
                      onChange={(e) => setIdName(e.target.value)}
                      placeholder="e.g., test_case_001"
                      className="w-full px-4 py-3 bg-black/30 border-2 border-orange-400/30 rounded-lg text-white placeholder-white/40 focus:border-orange-400 focus:outline-none"
                    />
                  </div>
                  
                  {/* Files to Persist Summary */}
                  <div className="mb-8 p-4 bg-white/5 rounded-lg border border-orange-400/30">
                    <h4 className="text-orange-200 font-semibold mb-2">📦 Files Ready to Persist:</h4>
                    <p className="text-white mb-2">
                      {payloadFiles.length} generated files (locators, pages, tests)
                    </p>
                    {payloadFiles.length > 0 && (
                      <div className="mt-2 text-sm text-orange-300/70 max-h-32 overflow-y-auto">
                        {payloadFiles.map((f: any, idx: number) => (
                          <div key={idx}>• {f.path}</div>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  {/* Success Message */}
                  {persistSuccess && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.8, y: -30 }}
                      animate={{ 
                        opacity: 1, 
                        scale: 1, 
                        y: 0,
                        transition: {
                          type: "spring",
                          stiffness: 300,
                          damping: 20
                        }
                      }}
                      exit={{ opacity: 0, scale: 0.8, y: -30 }}
                      className="mb-6 p-5 bg-gradient-to-br from-green-500/30 to-emerald-600/30 border-2 border-green-400 rounded-2xl shadow-2xl shadow-green-500/30 backdrop-blur-sm"
                    >
                      <div className="flex items-start gap-4">
                        <motion.div
                          initial={{ scale: 0, rotate: -180 }}
                          animate={{ 
                            scale: 1, 
                            rotate: 0,
                            transition: { delay: 0.2, type: "spring", stiffness: 200 }
                          }}
                        >
                          <CheckCircle2 size={28} className="text-green-400 flex-shrink-0 mt-1" />
                        </motion.div>
                        <div className="flex-1">
                          <motion.h4 
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0, transition: { delay: 0.3 } }}
                            className="text-green-300 font-bold text-lg mb-2"
                          >
                            Success! 🎉
                          </motion.h4>
                          <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1, transition: { delay: 0.4 } }}
                          >
                            <p className="text-white/90 flex items-center gap-2">
                              <span className="text-green-400">✓</span> Updated testmanager.xlsx
                            </p>
                            <p className="text-white/90 flex items-center gap-2">
                              <span className="text-green-400">✓</span> Persisted {persistSuccess.filesCount} files to repository
                            </p>
                            <motion.p 
                              className="text-green-300/80 text-sm mt-2 flex items-center gap-2"
                              animate={{ opacity: [0.5, 1, 0.5] }}
                              transition={{ duration: 1.5, repeat: Infinity }}
                            >
                              <Loader2 size={14} className="animate-spin" />
                              Proceeding to trial run...
                            </motion.p>
                          </motion.div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                  
                  {/* Error Message */}
                  {persistError && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.8, x: -30 }}
                      animate={{ 
                        opacity: 1, 
                        scale: 1, 
                        x: 0,
                        transition: {
                          type: "spring",
                          stiffness: 300,
                          damping: 20
                        }
                      }}
                      exit={{ opacity: 0, scale: 0.8, x: -30 }}
                      className="mb-6 p-5 bg-gradient-to-br from-red-500/30 to-rose-600/30 border-2 border-red-400 rounded-2xl shadow-2xl shadow-red-500/30 backdrop-blur-sm"
                    >
                      <div className="flex items-start gap-4">
                        <motion.div
                          animate={{ 
                            rotate: [0, -10, 10, -10, 0],
                            transition: { duration: 0.5, repeat: 2 }
                          }}
                        >
                          <AlertCircle size={28} className="text-red-400 flex-shrink-0 mt-1" />
                        </motion.div>
                        <div className="flex-1">
                          <h4 className="text-red-300 font-bold text-lg mb-2">Error</h4>
                          <p className="text-white/90">{persistError}</p>
                        </div>
                      </div>
                    </motion.div>
                  )}
                  
                  {/* Persist Button */}
                  <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={handlePersistFiles}
                    disabled={persisting || !testCaseId || !testCaseDescription}
                    className="w-full py-6 bg-gradient-to-r from-orange-600 to-amber-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-orange-500/50 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
                  >
                    {persisting ? (
                      <>
                        <Loader2 size={28} className="animate-spin" />
                        Updating TestManager...
                      </>
                    ) : (
                      <>
                        <Upload size={28} />
                        Update TestManager & Continue →
                      </>
                    )}
                  </motion.button>
                  
                  <p className="text-orange-300/60 text-sm mt-4 text-center">
                    {payloadFiles.length > 0 
                      ? 'This will update testmanager.xlsx and persist all generated files to the repository'
                      : 'This will update testmanager.xlsx for your existing test script'}
                  </p>
                  
                  {/* Back Button */}
                  <div className="mt-6 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={handleGoBack}
                      className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={20} />
                      Go Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION TRIAL RUN */}
          {currentStep === 'automation-trial-run' && (
            <motion.div
              key="automation-trial-run"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-4xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">Trial Run Execution</h2>
                
                <div className="bg-gradient-to-br from-indigo-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-indigo-500/30 rounded-3xl p-12">
                  {trialRunning ? (
                    <>
                      <div className="text-center mb-8">
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                          className="mb-8"
                        >
                          <Loader2 size={100} className="mx-auto text-indigo-400" />
                        </motion.div>
                        <h3 className="text-4xl font-bold text-white mb-4">Running trial execution...</h3>
                        <p className="text-xl text-indigo-200 mb-2">Chromium browser is executing your test automation</p>
                        <p className="text-sm text-indigo-300/60">Headed mode - you can see the browser actions</p>
                      </div>
                      
                      {/* Live Logs */}
                      {trialLogs && (
                        <div className="mb-6">
                          <h4 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                            <Circle size={16} className="text-indigo-400 animate-pulse" />
                            Live Execution Logs
                          </h4>
                          <div className="bg-black/40 rounded-lg p-4 max-h-96 overflow-y-auto border border-indigo-500/30">
                            <pre className="text-sm text-green-400 font-mono whitespace-pre-wrap">
                              {trialLogs}
                            </pre>
                          </div>
                        </div>
                      )}
                    </>
                  ) : trialResult ? (
                    <>
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: 'spring', stiffness: 200 }}
                        className="text-center mb-8"
                      >
                        {trialResult.success ? (
                          <CheckCircle2 size={100} className="mx-auto text-green-400 mb-6" />
                        ) : (
                          <Circle size={100} className="mx-auto text-red-400 mb-6" />
                        )}
                        <h3 className="text-4xl font-bold text-white mb-4">
                          {trialResult.success ? 'Trial Run Successful! ✅' : 'Trial Run Failed ❌'}
                        </h3>
                        <p className="text-xl text-indigo-200">{trialResult.message}</p>
                      </motion.div>
                      
                      {/* Final Logs */}
                      <div className="mb-8">
                        <h4 className="text-xl font-semibold text-white mb-4">Complete Execution Logs</h4>
                        <div className="bg-black/40 rounded-lg p-6 max-h-96 overflow-y-auto border border-indigo-500/30">
                          <pre className="text-sm text-indigo-300 font-mono whitespace-pre-wrap">
                            {trialLogs || trialResult.logs || 'No logs available'}
                          </pre>
                        </div>
                      </div>
                      
                      {/* Git Push Section */}
                      {trialResult.success && (
                        <div className="mb-8 p-6 bg-gradient-to-br from-green-900/20 to-emerald-800/20 border-2 border-green-500/30 rounded-2xl">
                          <h4 className="text-2xl font-bold text-white mb-4 flex items-center gap-3">
                            <GitBranch size={28} className="text-green-400" />
                            Push to Git
                          </h4>
                          <p className="text-green-200 mb-6">
                            Push your generated test scripts to the repository
                          </p>
                          
                          <div className="space-y-4 mb-6">
                            <div>
                              <label className="block text-green-200 mb-2 text-sm font-semibold">
                                Branch Name
                              </label>
                              <input
                                type="text"
                                value={gitBranch}
                                onChange={(e) => setGitBranch(e.target.value)}
                                placeholder="main"
                                className="w-full px-4 py-3 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-green-400 transition-all"
                              />
                            </div>
                            
                            <div>
                              <label className="block text-green-200 mb-2 text-sm font-semibold">
                                Commit Message
                              </label>
                              <input
                                type="text"
                                value={gitCommitMessage}
                                onChange={(e) => setGitCommitMessage(e.target.value)}
                                placeholder="Add automated test scripts"
                                className="w-full px-4 py-3 bg-white/10 backdrop-blur-md border-2 border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:border-green-400 transition-all"
                              />
                            </div>
                          </div>
                          
                          <motion.button
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={handleGitPush}
                            disabled={gitPushing}
                            className="w-full py-4 bg-gradient-to-r from-green-600 to-emerald-600 rounded-xl text-white text-lg font-semibold shadow-lg flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {gitPushing ? (
                              <>
                                <Loader2 size={24} className="animate-spin" />
                                Pushing to Git...
                              </>
                            ) : (
                              <>
                                <GitBranch size={24} />
                                Push Changes
                              </>
                            )}
                          </motion.button>
                          
                          {gitPushResult && (
                            <motion.div
                              initial={{ opacity: 0, y: -10 }}
                              animate={{ opacity: 1, y: 0 }}
                              className={`mt-4 p-4 rounded-lg border-2 ${
                                gitPushResult.success
                                  ? 'bg-green-900/40 border-green-500/60 text-green-200'
                                  : 'bg-red-900/40 border-red-500/60 text-red-200'
                              }`}
                            >
                              <div className="flex items-start gap-3">
                                {gitPushResult.success ? (
                                  <CheckCircle2 size={20} className="flex-shrink-0 mt-0.5" />
                                ) : (
                                  <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
                                )}
                                <span>{gitPushResult.message}</span>
                              </div>
                            </motion.div>
                          )}
                        </div>
                      )}
                      
                      <div className="flex gap-4">
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={handleTrialRun}
                          className="flex-1 py-6 bg-indigo-600 rounded-2xl text-white text-xl font-semibold shadow-lg flex items-center justify-center gap-2"
                        >
                          <Play size={24} />
                          Run Again
                        </motion.button>
                        <motion.button
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                          onClick={() => {
                            // If manual flow was already completed, skip the choice and go directly to completion
                            if (completedPaths.has('manual')) {
                              console.log('[Trial] Manual already done, going directly to completion');
                              setCurrentStep('completion');
                            } else {
                              setCurrentStep('automation-completion-choice');
                            }
                          }}
                          className="flex-1 py-6 bg-green-600 rounded-2xl text-white text-xl font-semibold shadow-lg flex items-center justify-center gap-2"
                        >
                          <CheckCircle2 size={24} />
                          Next
                        </motion.button>
                      </div>
                    </>
                  ) : (
                    <div className="text-center">
                      <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        onClick={handleTrialRun}
                        className="w-full py-6 bg-gradient-to-r from-indigo-600 to-purple-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-indigo-500/50 flex items-center justify-center gap-3"
                      >
                        <Play size={28} />
                        Start Trial Run →
                      </motion.button>
                    </div>
                  )}
                  
                  {/* Back Button */}
                  <div className="mt-6 text-center">
                    <motion.button
                      whileHover={{ x: -5 }}
                      onClick={handleGoBack}
                      className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                    >
                      <ArrowLeft size={20} />
                      Go Back
                    </motion.button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* AUTOMATION COMPLETION CHOICE */}
          {currentStep === 'automation-completion-choice' && (
            <motion.div
              key="automation-completion-choice"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-5xl mx-auto">
                <h2 className="text-5xl font-bold mb-12 text-center text-white">What Would You Like To Do Next?</h2>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* Manual Test Case Generation Card */}
                  <motion.button
                    whileHover={{ scale: 1.05, rotateY: 5 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => {
                      console.log('[CompletionChoice] Generate Manual clicked');
                      console.log('[CompletionChoice] completedPaths before:', Array.from(completedPaths));
                      
                      // Mark automation as completed
                      const newCompletedPaths = new Set(completedPaths).add('automation');
                      setCompletedPaths(newCompletedPaths);
                      
                      console.log('[CompletionChoice] Starting manual flow (automation already done)');
                      
                      // Always start the manual flow - don't skip it
                      setSelectedPath('manual');
                      setCurrentStep('manual-test');
                    }}
                    className="relative group"
                  >
                    <div className="h-full bg-gradient-to-br from-purple-900/40 to-purple-600/20 backdrop-blur-xl border-2 border-purple-500/30 rounded-3xl p-12 text-left hover:border-purple-400/60 transition-all shadow-2xl hover:shadow-purple-500/30">
                      <FileText size={80} className="text-purple-400 mb-6" />
                      <h3 className="text-4xl font-bold text-white mb-4">Generate Manual Test Cases</h3>
                      <p className="text-xl text-gray-300 mb-6">
                        Create comprehensive Excel-based manual test cases from your recorded flow
                      </p>
                      <ul className="space-y-3 text-gray-400">
                        <li className="flex items-start gap-3">
                          <CheckCircle2 size={20} className="text-purple-400 mt-1 flex-shrink-0" />
                          <span>Structured test case documentation</span>
                        </li>
                        <li className="flex items-start gap-3">
                          <CheckCircle2 size={20} className="text-purple-400 mt-1 flex-shrink-0" />
                          <span>Excel export for test management</span>
                        </li>
                        <li className="flex items-start gap-3">
                          <CheckCircle2 size={20} className="text-purple-400 mt-1 flex-shrink-0" />
                          <span>Detailed step-by-step instructions</span>
                        </li>
                      </ul>
                    </div>
                  </motion.button>

                  {/* Complete Task Card */}
                  <motion.button
                    whileHover={{ scale: 1.05, rotateY: 5 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setCurrentStep('completion')}
                    className="relative group"
                  >
                    <div className="h-full bg-gradient-to-br from-green-900/40 to-green-600/20 backdrop-blur-xl border-2 border-green-500/30 rounded-3xl p-12 text-left hover:border-green-400/60 transition-all shadow-2xl hover:shadow-green-500/30">
                      <CheckCircle2 size={80} className="text-green-400 mb-6" />
                      <h3 className="text-4xl font-bold text-white mb-4">Complete Task</h3>
                      <p className="text-xl text-gray-300 mb-6">
                        Finish your automation workflow and return to home
                      </p>
                      <ul className="space-y-3 text-gray-400">
                        <li className="flex items-start gap-3">
                          <CheckCircle2 size={20} className="text-green-400 mt-1 flex-shrink-0" />
                          <span>Automation test script generated</span>
                        </li>
                        <li className="flex items-start gap-3">
                          <CheckCircle2 size={20} className="text-green-400 mt-1 flex-shrink-0" />
                          <span>Trial run completed successfully</span>
                        </li>
                        <li className="flex items-start gap-3">
                          <CheckCircle2 size={20} className="text-green-400 mt-1 flex-shrink-0" />
                          <span>Ready to start a new session</span>
                        </li>
                      </ul>
                    </div>
                  </motion.button>
                </div>

                {/* Back Button */}
                <div className="mt-8 text-center">
                  <motion.button
                    whileHover={{ x: -5 }}
                    onClick={() => setCurrentStep('automation-trial-run')}
                    className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl text-white/60 hover:text-white hover:bg-white/10 transition-all flex items-center gap-2 mx-auto"
                  >
                    <ArrowLeft size={20} />
                    Back to Trial Run
                  </motion.button>
                </div>
              </div>
            </motion.div>
          )}

          {/* COMPLETION */}
          {currentStep === 'completion' && (
            <motion.div
              key="completion"
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
              custom={1}
              transition={{ duration: 0.8, type: 'spring', stiffness: 50 }}
              className="w-full px-6"
            >
              <div className="max-w-2xl mx-auto text-center">
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 200 }}
                  className="mb-12"
                >
                  <CheckCircle2 size={120} className="mx-auto text-green-400" />
                </motion.div>
                
                <h2 className="text-6xl font-bold text-white mb-6">Task Completed!</h2>
                <p className="text-2xl text-gray-300 mb-16">All workflows have been successfully executed.</p>
                
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleReturnHome}
                  className="px-12 py-6 bg-blue-600 rounded-2xl text-white text-2xl font-semibold shadow-2xl shadow-blue-500/50"
                >
                  Return to Home
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// Reusable Choice Card Component
function ChoiceCard({ 
  icon, 
  title, 
  subtitle, 
  color, 
  onClick, 
  delay 
}: { 
  icon: React.ReactNode; 
  title: string; 
  subtitle: string; 
  color: 'blue' | 'purple'; 
  onClick: () => void;
  delay: number;
}) {
  const colorClasses = {
    blue: {
      bg: 'from-blue-900/50 to-blue-600/30',
      border: 'border-blue-500/40',
      shadow: 'shadow-blue-500/30',
      hoverShadow: 'group-hover:shadow-blue-400/60',
      hoverBorder: 'group-hover:border-blue-400/60',
      text: 'text-blue-300',
      ringColor: 'border-blue-400/30',
    },
    purple: {
      bg: 'from-purple-900/50 to-pink-600/30',
      border: 'border-purple-500/40',
      shadow: 'shadow-purple-500/30',
      hoverShadow: 'group-hover:shadow-purple-400/60',
      hoverBorder: 'group-hover:border-purple-400/60',
      text: 'text-purple-300',
      ringColor: 'border-purple-400/30',
    },
  };

  const c = colorClasses[color];

  return (
    <motion.div
      initial={{ opacity: 0, x: color === 'blue' ? -150 : 150, rotateY: color === 'blue' ? -25 : 25, scale: 0.8 }}
      animate={{ opacity: 1, x: 0, rotateY: 0, scale: 1 }}
      transition={{ duration: 1.2, delay, type: 'spring', stiffness: 50 }}
      whileHover={{ scale: 1.1, y: -20, rotateY: color === 'blue' ? 8 : -8, rotateX: 5 }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      className="relative group cursor-pointer"
      style={{ perspective: '1500px', transformStyle: 'preserve-3d' }}
    >
      <div className={`relative bg-gradient-to-br ${c.bg} backdrop-blur-2xl border-2 ${c.border} rounded-[2.5rem] p-16 overflow-hidden shadow-2xl ${c.shadow} transition-all duration-700 ${c.hoverShadow} ${c.hoverBorder}`}>
        {/* Rotating Rings */}
        {[...Array(3)].map((_, i) => (
          <motion.div
            key={i}
            className={`absolute -top-24 -right-24 w-${40 + i * 8} h-${40 + i * 8} border-${i === 0 ? '[3px]' : '[2px]'} ${c.ringColor} rounded-full`}
            animate={{ rotate: i % 2 === 0 ? 360 : -360, scale: [1, 1.2 + i * 0.1, 1] }}
            transition={{ rotate: { duration: 20 + i * 5, repeat: Infinity, ease: 'linear' }, scale: { duration: 4 + i, repeat: Infinity } }}
          />
        ))}

        <div className="relative z-10 text-center">
          <motion.div
            animate={{ y: [0, -15, 0], rotateZ: [0, 8, -8, 0] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
            className={`mb-12 inline-block ${c.text}`}
            style={{ filter: `drop-shadow(0 0 30px ${color === 'blue' ? 'rgba(59, 130, 246, 0.7)' : 'rgba(168, 85, 247, 0.7)'})` }}
          >
            {icon}
          </motion.div>

          <h2 className="text-6xl font-bold mb-6 text-white drop-shadow-[0_0_30px_rgba(255,255,255,0.3)]">{title}</h2>
          <p className={`text-2xl ${color === 'blue' ? 'text-blue-100' : 'text-purple-100'} font-light tracking-wide`}>{subtitle}</p>

          <motion.div
            className={`mt-12 text-base ${color === 'blue' ? 'text-blue-300/80' : 'text-purple-300/80'} font-medium`}
            animate={{ opacity: [0.5, 1, 0.5], x: [0, 5, 0] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
          >
            Click to start →
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
}

// Record Button Component
function RecordButton({ onClick, isRecording }: { onClick: () => void; isRecording: boolean }) {
  return (
    <motion.div
      onClick={!isRecording ? onClick : undefined}
      className={`relative inline-block ${!isRecording ? 'cursor-pointer' : ''}`}
      whileHover={!isRecording ? { scale: 1.1 } : {}}
      whileTap={!isRecording ? { scale: 0.95 } : {}}
    >
      <div className="relative bg-gradient-to-br from-red-900/50 to-red-600/30 backdrop-blur-xl border-4 border-red-500/50 rounded-3xl p-12">
        {isRecording && (
          <>
            {[...Array(3)].map((_, i) => (
              <motion.div
                key={i}
                className="absolute inset-0 border-4 border-red-500/30 rounded-3xl"
                animate={{ scale: [1, 1.5, 2], opacity: [0.8, 0.3, 0] }}
                transition={{ duration: 2, repeat: Infinity, delay: i * 0.4 }}
              />
            ))}
          </>
        )}

        <motion.div
          animate={isRecording ? { scale: [1, 1.2, 1], opacity: [1, 0.7, 1] } : { y: [0, -5, 0] }}
          transition={isRecording ? { duration: 1.5, repeat: Infinity } : { duration: 2, repeat: Infinity }}
        >
          <Circle size={80} className="text-red-500" fill="currentColor" />
        </motion.div>
      </div>
    </motion.div>
  );
}

// Path Selection Card
function PathCard({ icon, title, description, color, isSelected, onClick }: any) {
  const c = color === 'blue' 
    ? { border: 'border-blue-500/40', bg: 'from-blue-900/40 to-blue-600/20', text: 'text-blue-200' }
    : { border: 'border-purple-500/40', bg: 'from-purple-900/40 to-purple-600/20', text: 'text-purple-200' };

  return (
    <motion.div
      whileHover={{ scale: 1.05, y: -10 }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      className={`relative cursor-pointer bg-gradient-to-br ${c.bg} backdrop-blur-xl border-2 ${c.border} ${isSelected ? 'ring-4 ring-white/50' : ''} rounded-3xl p-12 text-center transition-all duration-500`}
    >
      <div className={c.text}>{icon}</div>
      <h3 className="text-3xl font-bold text-white mt-8 mb-4">{title}</h3>
      <p className={`text-lg ${c.text}`}>{description}</p>
      {isSelected && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-4 -right-4 bg-white text-blue-600 rounded-full p-2"
        >
          <CheckCircle2 size={32} />
        </motion.div>
      )}
    </motion.div>
  );
}
