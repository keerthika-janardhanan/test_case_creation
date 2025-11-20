import { useState, useEffect } from "react";
import axios from "axios";
import { 
  Video, FileText, Code2, Loader2, Play, Sparkles, RotateCw, 
  ChevronRight, Check, Clock, Rocket, ArrowLeft, Github, FolderOpen,
  Settings, Download, Upload, GitBranch, TestTube
} from "lucide-react";
import "../styles/animated-dashboard.css";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

// Workflow states
const WORKFLOW_STATES = {
  HOME: 'home',
  RECORD_FORM: 'record_form',
  RECORDING: 'recording',
  RECORD_COMPLETE: 'record_complete',
  MANUAL_TEST_GENERATE: 'manual_test_generate',
  AUTOMATION_FORM: 'automation_form',
  AUTOMATION_OPTIONS: 'automation_options',
  SCRIPT_PREVIEW: 'script_preview',
  TEST_MANAGER_CONFIG: 'test_manager_config',
  TRIAL_RUN: 'trial_run'
};

const AnimatedDashboard = () => {
  // Main workflow state
  const [currentStep, setCurrentStep] = useState(WORKFLOW_STATES.HOME);
  const [workflowHistory, setWorkflowHistory] = useState<string[]>([]);

  // Recording states
  const [recordingData, setRecordingData] = useState({
    url: "",
    flow_name: "",
    timer: ""
  });
  const [currentRecording, setCurrentRecording] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingProgress, setRecordingProgress] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);

  // Automation states
  const [automationData, setAutomationData] = useState({
    repoUrl: "",
    scenario: "",
    keyword: ""
  });
  const [availableOptions, setAvailableOptions] = useState({
    existingScripts: [] as any[],
    refinedFlows: [] as any[]
  });
  const [selectedScriptOption, setSelectedScriptOption] = useState<'existing' | 'refined' | null>(null);
  const [scriptPreview, setScriptPreview] = useState("");
  const [editablePreview, setEditablePreview] = useState("");
  
  // Test Manager states
  const [testManagerData, setTestManagerData] = useState({
    apiUrl: "",
    username: "",
    password: ""
  });

  // Generation states
  const [generatedContent, setGeneratedContent] = useState<any>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isTrialRunning, setIsTrialRunning] = useState(false);

  // Navigation functions
  const navigateToStep = (step: string) => {
    setWorkflowHistory(prev => [...prev, currentStep]);
    setCurrentStep(step);
  };

  const goBack = () => {
    if (workflowHistory.length > 0) {
      const previousStep = workflowHistory[workflowHistory.length - 1];
      setWorkflowHistory(prev => prev.slice(0, -1));
      setCurrentStep(previousStep);
    }
  };

  const resetToHome = () => {
    setCurrentStep(WORKFLOW_STATES.HOME);
    setWorkflowHistory([]);
    // Reset all states
    setRecordingData({ url: "", flow_name: "", timer: "" });
    setAutomationData({ repoUrl: "", scenario: "", keyword: "" });
    setTestManagerData({ apiUrl: "", username: "", password: "" });
    setCurrentRecording(null);
    setIsRecording(false);
    setGeneratedContent(null);
    setSelectedScriptOption(null);
    setScriptPreview("");
    setEditablePreview("");
  };

  // Recording progress animation
  useEffect(() => {
    let interval: number;
    if (isRecording && recordingData.timer) {
      const totalTime = parseInt(recordingData.timer);
      const startTime = Date.now();
      
      interval = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        setElapsedTime(Math.floor(elapsed));
        const progress = Math.min((elapsed / totalTime) * 100, 100);
        setRecordingProgress(progress);
        
        if (progress >= 100) {
          setIsRecording(false);
          setCurrentStep(WORKFLOW_STATES.RECORD_COMPLETE);
          clearInterval(interval);
        }
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isRecording, recordingData.timer]);

  // API functions
  const handleStartRecording = async () => {
    if (!recordingData.url || !recordingData.flow_name || !recordingData.timer) {
      alert("Please fill in all fields");
      return;
    }

    try {
      setIsRecording(true);
      setCurrentStep(WORKFLOW_STATES.RECORDING);
      
      const response = await axios.post(`${API}/recordings`, {
        url: recordingData.url,
        flow_name: recordingData.flow_name,
        timer: parseInt(recordingData.timer)
      });
      setCurrentRecording(response.data.id);
    } catch (error) {
      console.error("Error starting recording:", error);
      setIsRecording(false);
    }
  };

  const handleGenerateManualTest = async () => {
    setIsGenerating(true);
    try {
      const response = await axios.post(`${API}/recordings/generate-manual-test`, {
        recording_id: currentRecording,
        format: "markdown"
      });
      setGeneratedContent({
        type: "manual",
        content: response.data.test_case
      });
    } catch (error) {
      console.error("Error generating test case:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  const checkAutomationOptions = async () => {
    setIsGenerating(true);
    try {
      // Check for existing scripts
      const existingResponse = await axios.get(`${API}/automation/existing-scripts`, {
        params: { repoUrl: automationData.repoUrl, scenario: automationData.scenario }
      });
      
      // Check for refined flows
      const flowsResponse = await axios.get(`${API}/recordings/refined-flows`, {
        params: { recording_id: currentRecording }
      });

      setAvailableOptions({
        existingScripts: existingResponse.data.scripts || [],
        refinedFlows: flowsResponse.data.flows || []
      });
      
      setCurrentStep(WORKFLOW_STATES.AUTOMATION_OPTIONS);
    } catch (error) {
      console.error("Error checking automation options:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleScriptGeneration = async () => {
    setIsGenerating(true);
    try {
      if (selectedScriptOption === 'existing') {
        // Use existing script
        setCurrentStep(WORKFLOW_STATES.TEST_MANAGER_CONFIG);
      } else {
        // Generate from refined flow
        const response = await axios.post(`${API}/automation/generate-script`, {
          recording_id: currentRecording,
          feedback: editablePreview
        });
        setScriptPreview(response.data.script);
        setCurrentStep(WORKFLOW_STATES.SCRIPT_PREVIEW);
      }
    } catch (error) {
      console.error("Error generating script:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleTrialRun = async () => {
    setIsTrialRunning(true);
    try {
      await axios.post(`${API}/trial/run`, {
        testManagerData,
        selectedScript: selectedScriptOption === 'existing' ? 'existing' : scriptPreview
      });
      
      // Trial run completed
      alert("Trial run completed successfully!");
    } catch (error) {
      console.error("Error running trial:", error);
    } finally {
      setIsTrialRunning(false);
    }
  };

  const handlePushToRepo = async () => {
    try {
      await axios.post(`${API}/automation/push`, {
        script: scriptPreview,
        repoUrl: automationData.repoUrl
      });
      alert("Script pushed to repository successfully!");
      resetToHome();
    } catch (error) {
      console.error("Error pushing to repo:", error);
    }
  };

  return (
    <div className="dashboard-content">
      {/* Sparkle particles */}
      <div className="sparkle-container">
        <div className="sparkle sparkle-1"></div>
        <div className="sparkle sparkle-2"></div>
        <div className="sparkle sparkle-3"></div>
        <div className="sparkle sparkle-4"></div>
        <div className="sparkle sparkle-5"></div>
      </div>
      
      {/* Main Content */}
      <main className="relative z-10 p-6">
        {/* Back Button */}
        {currentStep !== WORKFLOW_STATES.HOME && (
          <div className="mb-6">
            <button
              onClick={goBack}
              className="flex items-center gap-2 px-4 py-2 bg-white/20 hover:bg-white/30 hover:scale-105 transition-all duration-300 rounded-xl shadow-lg border border-white/30 font-semibold text-white backdrop-blur-sm"
              style={{ fontFamily: 'Nunito, sans-serif' }}
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
          </div>
        )}
        {/* HOME - Initial 3 Options */}
        {currentStep === WORKFLOW_STATES.HOME && (
          <div className="max-w-6xl mx-auto">
            <div className="text-center mb-12 float-in">
              <h2 className="text-5xl font-bold text-slate-800 mb-4" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                Choose Your Journey
              </h2>
              <p className="text-xl text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                Select an option to get started with test automation
              </p>
            </div>
            
            <div className="grid md:grid-cols-3 gap-8">
              {/* Option 1: Record Flow */}
              <div 
                className="cursor-pointer border-3 border-white/60 bg-white/80 backdrop-blur-sm shadow-2xl hover:shadow-3xl card-hover-float group relative overflow-hidden rounded-3xl"
                onClick={() => navigateToStep(WORKFLOW_STATES.RECORD_FORM)}
              >
                <div className="gradient-overlay"></div>
                <div className="text-center pb-8 pt-8 relative z-10">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-violet-500 via-fuchsia-500 to-pink-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 transition-transform duration-500 pulse-glow rotate-animation">
                    <Video className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-3xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Record Flow</h3>
                  <p className="text-base mb-6 px-4 text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Start a new screen recording session to capture user interactions
                  </p>
                  <div className="inline-flex items-center gap-3 px-6 py-3 bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white rounded-full font-bold shadow-xl group-hover:shadow-2xl transition-all duration-300 hover:scale-110">
                    Record Now
                    <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>

              {/* Option 2: Generate Manual Test Cases */}
              <div 
                className="cursor-pointer border-3 border-white/60 bg-white/80 backdrop-blur-sm shadow-2xl hover:shadow-3xl card-hover-float group relative overflow-hidden rounded-3xl"
                onClick={() => navigateToStep(WORKFLOW_STATES.MANUAL_TEST_GENERATE)}
              >
                <div className="gradient-overlay"></div>
                <div className="text-center pb-8 pt-8 relative z-10">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 transition-transform duration-500 pulse-glow-blue">
                    <FileText className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-3xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Manual Test Cases</h3>
                  <p className="text-base mb-6 px-4 text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Generate detailed manual test case documents from existing recordings
                  </p>
                  <div className="inline-flex items-center gap-3 px-6 py-3 bg-gradient-to-r from-blue-500 to-cyan-500 text-white rounded-full font-bold shadow-xl group-hover:shadow-2xl transition-all duration-300 hover:scale-110">
                    Generate Tests
                    <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>

              {/* Option 3: Generate Automation Scripts */}
              <div 
                className="cursor-pointer border-3 border-white/60 bg-white/80 backdrop-blur-sm shadow-2xl hover:shadow-3xl card-hover-float group relative overflow-hidden rounded-3xl"
                onClick={() => navigateToStep(WORKFLOW_STATES.AUTOMATION_FORM)}
              >
                <div className="gradient-overlay"></div>
                <div className="text-center pb-8 pt-8 relative z-10">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-purple-500 to-pink-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 transition-transform duration-500 pulse-glow-purple">
                    <Code2 className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-3xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Automation Scripts</h3>
                  <p className="text-base mb-6 px-4 text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Generate Playwright automation scripts for your test scenarios
                  </p>
                  <div className="inline-flex items-center gap-3 px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-full font-bold shadow-xl group-hover:shadow-2xl transition-all duration-300 hover:scale-110">
                    Create Scripts
                    <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* RECORD_FORM - Recording Configuration */}
        {currentStep === WORKFLOW_STATES.RECORD_FORM && (
          <div className="max-w-2xl mx-auto slide-up">
            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              <div className="gradient-border"></div>
              
              <div className="p-8">
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-16 h-16 bg-gradient-to-br from-violet-500 via-fuchsia-500 to-pink-500 rounded-2xl flex items-center justify-center shadow-lg pulse-glow">
                    <Video className="w-8 h-8 text-white" />
                  </div>
                  <div>
                    <h2 className="text-3xl font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Recording Setup</h2>
                    <p className="text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      Configure your recording session
                    </p>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="space-y-3 input-float" style={{ animationDelay: '0.1s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-violet-100 rounded-full flex items-center justify-center text-violet-600 text-sm font-bold">1</span>
                      Website URL
                    </label>
                    <input
                      type="url"
                      placeholder="https://example.com"
                      value={recordingData.url}
                      onChange={(e) => setRecordingData({ ...recordingData, url: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-violet-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="space-y-3 input-float" style={{ animationDelay: '0.2s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-fuchsia-100 rounded-full flex items-center justify-center text-fuchsia-600 text-sm font-bold">2</span>
                      Flow Name
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., Login Flow"
                      value={recordingData.flow_name}
                      onChange={(e) => setRecordingData({ ...recordingData, flow_name: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-fuchsia-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="space-y-3 input-float" style={{ animationDelay: '0.3s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-pink-100 rounded-full flex items-center justify-center text-pink-600 text-sm font-bold">3</span>
                      Recording Duration (seconds)
                    </label>
                    <input
                      type="number"
                      placeholder="30"
                      value={recordingData.timer}
                      onChange={(e) => setRecordingData({ ...recordingData, timer: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-pink-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="flex gap-4 pt-6">
                    <button
                      onClick={handleStartRecording}
                      className="flex-1 h-14 bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600 hover:from-violet-700 hover:via-fuchsia-700 hover:to-pink-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center justify-center gap-3"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    >
                      <Play className="w-5 h-5" />
                      Start Recording
                      <Rocket className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* RECORDING - Recording in Progress */}
        {currentStep === WORKFLOW_STATES.RECORDING && (
          <div className="max-w-2xl mx-auto slide-up">
            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              <div className="p-12 text-center space-y-8">
                <div className="relative inline-block">
                  <div className="w-32 h-32 mx-auto bg-gradient-to-br from-violet-500 via-fuchsia-500 to-pink-500 rounded-full flex items-center justify-center shadow-2xl recording-pulse">
                    <Video className="w-16 h-16 text-white animate-pulse" />
                  </div>
                  <div className="absolute -top-2 -right-2">
                    <div className="w-8 h-8 bg-red-500 rounded-full flex items-center justify-center shadow-lg recording-dot">
                      <div className="w-3 h-3 bg-white rounded-full"></div>
                    </div>
                  </div>
                </div>
                
                <div className="space-y-4">
                  <h3 className="text-3xl font-bold text-slate-800" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                    Recording in Progress...
                  </h3>
                  <div className="flex items-center justify-center gap-3 text-slate-600">
                    <Clock className="w-5 h-5" />
                    <span className="text-xl font-semibold" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      {elapsedTime}s / {recordingData.timer}s
                    </span>
                  </div>
                </div>
                
                <div className="max-w-md mx-auto space-y-3">
                  <div className="h-3 bg-slate-200 rounded-full overflow-hidden">
                    <div 
                      className="h-full progress-animated rounded-full transition-all duration-300"
                      style={{ width: `${recordingProgress}%` }}
                    ></div>
                  </div>
                  <p className="text-sm text-slate-500" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    {Math.round(recordingProgress)}% Complete
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* RECORD_COMPLETE - Recording Finished, Show Next Options */}
        {currentStep === WORKFLOW_STATES.RECORD_COMPLETE && (
          <div className="max-w-4xl mx-auto space-y-8 fade-in">
            <div className="border-3 border-emerald-200 bg-gradient-to-r from-emerald-50 to-teal-50 rounded-3xl card-float relative overflow-hidden shadow-2xl">
              <div className="success-confetti"></div>
              <div className="text-center p-8">
                <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-full flex items-center justify-center shadow-xl bounce-in success-icon">
                  <Check className="w-10 h-10 text-white" />
                </div>
                <h2 className="text-4xl text-emerald-800 mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                  Recording Completed Successfully!
                </h2>
                <p className="text-xl text-emerald-700" style={{ fontFamily: 'Nunito, sans-serif' }}>
                  Choose your next step ✨
                </p>
              </div>
            </div>

            {/* Next Step Options */}
            <div className="grid md:grid-cols-2 gap-8">
              {/* Manual Test Cases */}
              <div
                className="cursor-pointer border-3 border-white/60 bg-white/80 backdrop-blur-sm shadow-xl card-hover-bounce group transition-all duration-500 relative overflow-hidden rounded-3xl"
                onClick={() => {
                  setCurrentStep(WORKFLOW_STATES.MANUAL_TEST_GENERATE);
                  handleGenerateManualTest();
                }}
              >
                <div className="text-center p-8">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 group-hover:rotate-6 transition-all duration-500 pulse-glow-blue icon-3d">
                    <FileText className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-2xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                    Generate Manual Test Case
                  </h3>
                  <p className="text-base px-4 text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Create detailed manual test case documentation
                  </p>
                </div>
              </div>

              {/* Automation Scripts */}
              <div
                className="cursor-pointer border-3 border-white/60 bg-white/80 backdrop-blur-sm shadow-xl card-hover-bounce group transition-all duration-500 relative overflow-hidden rounded-3xl"
                onClick={() => navigateToStep(WORKFLOW_STATES.AUTOMATION_FORM)}
              >
                <div className="text-center p-8">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-purple-500 to-pink-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 group-hover:-rotate-6 transition-all duration-500 pulse-glow-purple icon-3d">
                    <Code2 className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-2xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                    Generate Automation Scripts
                  </h3>
                  <p className="text-base px-4 text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Create Playwright automation code
                  </p>
                </div>
              </div>
            </div>

            {/* Reset Option */}
            <div className="text-center pt-6">
              <button
                onClick={resetToHome}
                className="px-8 py-4 border-3 border-white/60 hover:bg-white hover:scale-105 transition-all duration-300 shadow-lg font-bold text-lg rounded-xl bg-white/80"
                style={{ fontFamily: 'Nunito, sans-serif' }}
              >
                <RotateCw className="w-5 h-5 mr-2 inline" />
                Start New Session
              </button>
            </div>
          </div>
        )}

        {/* Continue with other workflow states... */}

        {/* MANUAL_TEST_GENERATE - Generating Manual Test */}
        {currentStep === WORKFLOW_STATES.MANUAL_TEST_GENERATE && (
          <div className="max-w-2xl mx-auto slide-up">
            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              {isGenerating ? (
                <div className="p-20 text-center">
                  <div className="relative inline-block mb-6">
                    <Loader2 className="w-16 h-16 mx-auto animate-spin text-blue-600" />
                    <Sparkles className="w-8 h-8 absolute -top-3 -right-3 text-cyan-500 sparkle-spin" />
                  </div>
                  <h3 className="text-2xl text-slate-700 font-bold mb-3" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                    Generating Manual Test Case...
                  </h3>
                  <p className="text-base text-slate-500" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Creating detailed test documentation ✨
                  </p>
                </div>
              ) : (
                <div className="p-8">
                  <div className="flex items-center gap-4 mb-6">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-2xl flex items-center justify-center shadow-lg pulse-glow-blue">
                      <FileText className="w-8 h-8 text-white" />
                    </div>
                    <div>
                      <h2 className="text-3xl font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Manual Test Case Generated</h2>
                      <p className="text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>Ready for review and download</p>
                    </div>
                  </div>

                  {generatedContent && (
                    <div className="space-y-6">
                      <div className="bg-slate-900 rounded-2xl p-6 shadow-inner overflow-hidden relative">
                        <div className="code-glow"></div>
                        <pre className="text-slate-100 overflow-x-auto text-sm relative z-10 max-h-96" style={{ fontFamily: 'monospace' }}>
                          {generatedContent.content}
                        </pre>
                      </div>
                      
                      <div className="flex gap-4">
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(generatedContent.content);
                            alert("Copied to clipboard!");
                          }}
                          className="flex-1 h-12 bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-700 hover:to-cyan-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 rounded-xl flex items-center justify-center gap-3"
                          style={{ fontFamily: 'Nunito, sans-serif' }}
                        >
                          <Download className="w-4 h-4" />
                          Copy to Clipboard
                        </button>
                        
                        <button
                          onClick={resetToHome}
                          className="px-6 h-12 border-3 border-white/60 hover:bg-white hover:scale-105 transition-all duration-300 shadow-lg font-bold rounded-xl bg-white/80"
                          style={{ fontFamily: 'Nunito, sans-serif' }}
                        >
                          <RotateCw className="w-4 h-4 mr-2 inline" />
                          New Session
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* AUTOMATION_FORM - Repository Details Form */}
        {currentStep === WORKFLOW_STATES.AUTOMATION_FORM && (
          <div className="max-w-2xl mx-auto slide-up">
            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              <div className="gradient-border"></div>
              
              <div className="p-8">
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl flex items-center justify-center shadow-lg pulse-glow-purple">
                    <Github className="w-8 h-8 text-white" />
                  </div>
                  <div>
                    <h2 className="text-3xl font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Automation Setup</h2>
                    <p className="text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      Configure repository and scenario details
                    </p>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="space-y-3 input-float" style={{ animationDelay: '0.1s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center text-purple-600 text-sm font-bold">1</span>
                      Repository URL
                    </label>
                    <input
                      type="url"
                      placeholder="https://github.com/your-org/your-repo"
                      value={automationData.repoUrl}
                      onChange={(e) => setAutomationData({ ...automationData, repoUrl: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-purple-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="space-y-3 input-float" style={{ animationDelay: '0.2s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-pink-100 rounded-full flex items-center justify-center text-pink-600 text-sm font-bold">2</span>
                      Scenario/Test Case ID
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., TC001 or Login Scenario"
                      value={automationData.scenario}
                      onChange={(e) => setAutomationData({ ...automationData, scenario: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-pink-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="space-y-3 input-float" style={{ animationDelay: '0.3s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-violet-100 rounded-full flex items-center justify-center text-violet-600 text-sm font-bold">3</span>
                      Keywords (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., login, authentication"
                      value={automationData.keyword}
                      onChange={(e) => setAutomationData({ ...automationData, keyword: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-violet-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="flex gap-4 pt-6">
                    <button
                      onClick={checkAutomationOptions}
                      disabled={!automationData.repoUrl || !automationData.scenario || isGenerating}
                      className="flex-1 h-14 bg-gradient-to-r from-purple-600 via-pink-600 to-violet-600 hover:from-purple-700 hover:via-pink-700 hover:to-violet-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    >
                      {isGenerating ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          Checking...
                        </>
                      ) : (
                        <>
                          <FolderOpen className="w-5 h-5" />
                          Check Repository
                          <Sparkles className="w-5 h-5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* AUTOMATION_OPTIONS - Choose Between Existing Scripts and Refined Flows */}
        {currentStep === WORKFLOW_STATES.AUTOMATION_OPTIONS && (
          <div className="max-w-4xl mx-auto space-y-8 fade-in">
            <div className="text-center mb-8">
              <h2 className="text-4xl font-bold text-slate-800 mb-4" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                Choose Your Script Source
              </h2>
              <p className="text-xl text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                We found the following options in your repository
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-8">
              {/* Existing Scripts Option */}
              <div
                className={`cursor-pointer border-3 bg-white/80 backdrop-blur-sm shadow-xl card-hover-bounce group transition-all duration-500 relative overflow-hidden rounded-3xl ${
                  selectedScriptOption === 'existing' ? 'border-green-400 scale-105 shadow-2xl ring-4 ring-green-200' : 'border-white/60 hover:shadow-2xl'
                }`}
                onClick={() => setSelectedScriptOption('existing')}
              >
                {selectedScriptOption === 'existing' && <div className="selected-shimmer"></div>}
                
                <div className="text-center p-8">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-green-500 to-emerald-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 transition-all duration-500 pulse-glow icon-3d">
                    <GitBranch className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-2xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                    Use Existing Scripts
                  </h3>
                  <p className="text-base px-4 text-slate-600 mb-4" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Found {availableOptions.existingScripts.length} existing test scripts
                  </p>
                  {availableOptions.existingScripts.length > 0 ? (
                    <div className="text-sm text-green-600 font-semibold bg-green-50 rounded-lg p-3">
                      Ready to configure and run trials
                    </div>
                  ) : (
                    <div className="text-sm text-slate-500 bg-slate-50 rounded-lg p-3">
                      No existing scripts found
                    </div>
                  )}
                </div>
              </div>

              {/* Refined Flow Option */}
              <div
                className={`cursor-pointer border-3 bg-white/80 backdrop-blur-sm shadow-xl card-hover-bounce group transition-all duration-500 relative overflow-hidden rounded-3xl ${
                  selectedScriptOption === 'refined' ? 'border-blue-400 scale-105 shadow-2xl ring-4 ring-blue-200' : 'border-white/60 hover:shadow-2xl'
                }`}
                onClick={() => setSelectedScriptOption('refined')}
              >
                {selectedScriptOption === 'refined' && <div className="selected-shimmer"></div>}
                
                <div className="text-center p-8">
                  <div className="w-24 h-24 mx-auto mb-6 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-3xl flex items-center justify-center shadow-2xl group-hover:scale-110 transition-all duration-500 pulse-glow-blue icon-3d">
                    <Sparkles className="w-12 h-12 text-white" />
                  </div>
                  <h3 className="text-2xl mb-3 font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                    Use Refined Recording Flow
                  </h3>
                  <p className="text-base px-4 text-slate-600 mb-4" style={{ fontFamily: 'Nunito, sans-serif' }}>
                    Generate new script from your recording session
                  </p>
                  {availableOptions.refinedFlows.length > 0 ? (
                    <div className="text-sm text-blue-600 font-semibold bg-blue-50 rounded-lg p-3">
                      Recording flow available for customization
                    </div>
                  ) : (
                    <div className="text-sm text-slate-500 bg-slate-50 rounded-lg p-3">
                      No refined flows found
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Continue Button */}
            {selectedScriptOption && (
              <div className="text-center pt-6 scale-in">
                <button
                  onClick={handleScriptGeneration}
                  disabled={isGenerating}
                  className="px-8 py-4 bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-700 hover:to-fuchsia-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center gap-3 mx-auto"
                  style={{ fontFamily: 'Nunito, sans-serif' }}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      Continue with {selectedScriptOption === 'existing' ? 'Existing Scripts' : 'Refined Flow'}
                      <ChevronRight className="w-5 h-5" />
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}

        {/* SCRIPT_PREVIEW - Editable Preview for Refined Flow */}
        {currentStep === WORKFLOW_STATES.SCRIPT_PREVIEW && (
          <div className="max-w-4xl mx-auto space-y-8 fade-in">
            <div className="text-center mb-8">
              <h2 className="text-4xl font-bold text-slate-800 mb-4" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                Script Preview & Feedback
              </h2>
              <p className="text-xl text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                Review and customize your generated script
              </p>
            </div>

            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              <div className="p-8">
                <div className="flex items-center gap-4 mb-6">
                  <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-500 rounded-2xl flex items-center justify-center shadow-lg pulse-glow">
                    <Code2 className="w-8 h-8 text-white" />
                  </div>
                  <div>
                    <h3 className="text-3xl font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Generated Script</h3>
                    <p className="text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>Make any necessary adjustments</p>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="bg-slate-900 rounded-2xl p-6 shadow-inner overflow-hidden relative">
                    <div className="code-glow"></div>
                    <textarea
                      value={editablePreview || scriptPreview}
                      onChange={(e) => setEditablePreview(e.target.value)}
                      className="w-full h-96 bg-transparent text-slate-100 resize-none outline-none text-sm relative z-10"
                      style={{ fontFamily: 'monospace' }}
                      placeholder="Generated script will appear here..."
                    />
                  </div>

                  <div className="flex gap-4">
                    <button
                      onClick={() => setCurrentStep(WORKFLOW_STATES.TEST_MANAGER_CONFIG)}
                      className="flex-1 h-14 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center justify-center gap-3"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    >
                      <Check className="w-5 h-5" />
                      Approve Script
                      <ChevronRight className="w-5 h-5" />
                    </button>
                    
                    <button
                      onClick={goBack}
                      className="px-6 h-14 border-3 border-white/60 hover:bg-white hover:scale-105 transition-all duration-300 shadow-lg font-bold text-lg rounded-xl bg-white/80"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    >
                      Edit More
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TEST_MANAGER_CONFIG - Test Manager Configuration */}
        {currentStep === WORKFLOW_STATES.TEST_MANAGER_CONFIG && (
          <div className="max-w-2xl mx-auto slide-up">
            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              <div className="gradient-border"></div>
              
              <div className="p-8">
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-16 h-16 bg-gradient-to-br from-orange-500 to-red-500 rounded-2xl flex items-center justify-center shadow-lg pulse-glow">
                    <Settings className="w-8 h-8 text-white" />
                  </div>
                  <div>
                    <h2 className="text-3xl font-bold" style={{ fontFamily: 'Fredoka, sans-serif' }}>Test Configuration</h2>
                    <p className="text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      Configure testmanager.xlsx credentials
                    </p>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="space-y-3 input-float" style={{ animationDelay: '0.1s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center text-orange-600 text-sm font-bold">1</span>
                      API URL
                    </label>
                    <input
                      type="url"
                      placeholder="https://your-app.domain.com"
                      value={testManagerData.apiUrl}
                      onChange={(e) => setTestManagerData({ ...testManagerData, apiUrl: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-orange-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="space-y-3 input-float" style={{ animationDelay: '0.2s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-red-100 rounded-full flex items-center justify-center text-red-600 text-sm font-bold">2</span>
                      Username
                    </label>
                    <input
                      type="text"
                      placeholder="test.user@example.com"
                      value={testManagerData.username}
                      onChange={(e) => setTestManagerData({ ...testManagerData, username: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-red-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="space-y-3 input-float" style={{ animationDelay: '0.3s' }}>
                    <label className="text-sm font-semibold flex items-center gap-2" style={{ fontFamily: 'Nunito, sans-serif' }}>
                      <span className="w-8 h-8 bg-pink-100 rounded-full flex items-center justify-center text-pink-600 text-sm font-bold">3</span>
                      Password
                    </label>
                    <input
                      type="password"
                      placeholder="••••••••"
                      value={testManagerData.password}
                      onChange={(e) => setTestManagerData({ ...testManagerData, password: e.target.value })}
                      className="w-full h-12 px-4 border-2 border-white/60 rounded-xl focus:border-pink-400 bg-white/50 transition-all duration-300 focus:scale-[1.02] outline-none"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    />
                  </div>

                  <div className="flex gap-4 pt-6">
                    <button
                      onClick={() => setCurrentStep(WORKFLOW_STATES.TRIAL_RUN)}
                      disabled={!testManagerData.apiUrl || !testManagerData.username || !testManagerData.password}
                      className="flex-1 h-14 bg-gradient-to-r from-orange-600 via-red-600 to-pink-600 hover:from-orange-700 hover:via-red-700 hover:to-pink-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center justify-center gap-3 disabled:opacity-50 disabled:cursor-not-allowed"
                      style={{ fontFamily: 'Nunito, sans-serif' }}
                    >
                      <TestTube className="w-5 h-5" />
                      Start Trial Run
                      <Rocket className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TRIAL_RUN - Trial Execution */}
        {currentStep === WORKFLOW_STATES.TRIAL_RUN && (
          <div className="max-w-4xl mx-auto space-y-8 fade-in">
            <div className="text-center mb-8">
              <h2 className="text-4xl font-bold text-slate-800 mb-4" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                Trial Run Execution
              </h2>
              <p className="text-xl text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                Testing your automation script
              </p>
            </div>

            <div className="border-3 border-white/60 bg-white/90 backdrop-blur-md shadow-2xl rounded-3xl card-float relative overflow-hidden">
              <div className="p-12 text-center">
                {isTrialRunning ? (
                  <div className="space-y-8">
                    <div className="relative inline-block">
                      <div className="w-32 h-32 mx-auto bg-gradient-to-br from-green-500 via-emerald-500 to-teal-500 rounded-full flex items-center justify-center shadow-2xl recording-pulse">
                        <TestTube className="w-16 h-16 text-white animate-pulse" />
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      <h3 className="text-3xl font-bold text-slate-800" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                        Trial Run in Progress...
                      </h3>
                      <p className="text-xl text-slate-600" style={{ fontFamily: 'Nunito, sans-serif' }}>
                        Chromium browser is executing your test script
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-8">
                    <div className="w-20 h-20 mx-auto mb-6 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center shadow-xl success-icon">
                      <Check className="w-10 h-10 text-white" />
                    </div>
                    
                    <div>
                      <h3 className="text-3xl font-bold text-emerald-800 mb-4" style={{ fontFamily: 'Fredoka, sans-serif' }}>
                        Trial Run Completed Successfully!
                      </h3>
                      <p className="text-xl text-emerald-700 mb-8" style={{ fontFamily: 'Nunito, sans-serif' }}>
                        Your automation script is working perfectly
                      </p>
                    </div>

                    <div className="flex gap-4 justify-center">
                      <button
                        onClick={handlePushToRepo}
                        className="px-8 py-4 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center gap-3"
                        style={{ fontFamily: 'Nunito, sans-serif' }}
                      >
                        <Upload className="w-5 h-5" />
                        Push to Repository
                      </button>
                      
                      <button
                        onClick={resetToHome}
                        className="px-8 py-4 border-3 border-white/60 hover:bg-white hover:scale-105 transition-all duration-300 shadow-lg font-bold text-lg rounded-xl bg-white/80"
                        style={{ fontFamily: 'Nunito, sans-serif' }}
                      >
                        <RotateCw className="w-5 h-5 mr-2 inline" />
                        New Session
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
            
            {/* Start Trial Button */}
            {!isTrialRunning && currentStep === WORKFLOW_STATES.TRIAL_RUN && !generatedContent?.trialCompleted && (
              <div className="text-center">
                <button
                  onClick={handleTrialRun}
                  className="px-8 py-4 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white font-bold shadow-lg hover:shadow-xl hover:scale-105 transition-all duration-300 text-lg rounded-xl flex items-center gap-3 mx-auto"
                  style={{ fontFamily: 'Nunito, sans-serif' }}
                >
                  <Play className="w-5 h-5" />
                  Start Trial Run
                  <TestTube className="w-5 h-5" />
                </button>
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
};

export default AnimatedDashboard;