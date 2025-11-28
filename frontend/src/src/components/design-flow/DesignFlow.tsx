import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RecorderSection } from './RecorderSection';
import { ChoiceSection } from './ChoiceSection';
import { ManualTestCaseFlow } from './ManualTestCaseFlow';
import { AutomationScriptFlow } from './AutomationScriptFlow';

export type DesignStep = 
  | 'recorder'
  | 'choice'
  | 'manual-testcase'
  | 'automation-script'
  | 'secondary-choice-after-manual'
  | 'secondary-choice-after-automation'
  | 'complete';

export interface DesignFlowState {
  currentStep: DesignStep;
  recordingCompleted: boolean;
  manualTestCaseCompleted: boolean;
  automationScriptCompleted: boolean;
  sessionName?: string;
}

export const DesignFlow: React.FC = () => {
  const [flowState, setFlowState] = useState<DesignFlowState>({
    currentStep: 'recorder',
    recordingCompleted: false,
    manualTestCaseCompleted: false,
    automationScriptCompleted: false,
  });

  const handleRecordingComplete = (sessionName: string) => {
    setFlowState({
      ...flowState,
      recordingCompleted: true,
      currentStep: 'choice',
      sessionName,
    });
  };

  const handleChoice = (choice: 'manual' | 'automation') => {
    if (choice === 'manual') {
      setFlowState({
        ...flowState,
        currentStep: 'manual-testcase',
      });
    } else {
      setFlowState({
        ...flowState,
        currentStep: 'automation-script',
      });
    }
  };

  const handleManualTestCaseComplete = () => {
    setFlowState({
      ...flowState,
      manualTestCaseCompleted: true,
      currentStep: 'secondary-choice-after-manual',
    });
  };

  const handleAutomationScriptComplete = () => {
    setFlowState({
      ...flowState,
      automationScriptCompleted: true,
      currentStep: 'secondary-choice-after-automation',
    });
  };

  const handleSecondaryChoice = (choice: 'continue' | 'complete') => {
    if (choice === 'complete') {
      setFlowState({
        ...flowState,
        currentStep: 'complete',
      });
    } else {
      // If after manual, go to automation; if after automation, go to manual
      if (flowState.currentStep === 'secondary-choice-after-manual') {
        setFlowState({
          ...flowState,
          currentStep: 'automation-script',
        });
      } else {
        setFlowState({
          ...flowState,
          currentStep: 'manual-testcase',
        });
      }
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-slate-900 to-black relative overflow-hidden">
      <AnimatePresence mode="wait">
        {flowState.currentStep === 'recorder' && (
          <RecorderSection
            key="recorder"
            onComplete={handleRecordingComplete}
          />
        )}

        {flowState.currentStep === 'choice' && (
          <ChoiceSection
            key="choice"
            onChoice={handleChoice}
            title="Choose Your Next Step"
            option1="Generate Manual Test Cases"
            option2="Generate Automation Scripts"
          />
        )}

        {flowState.currentStep === 'manual-testcase' && (
          <ManualTestCaseFlow
            key="manual-testcase"
            sessionName={flowState.sessionName}
            onComplete={handleManualTestCaseComplete}
          />
        )}

        {flowState.currentStep === 'automation-script' && (
          <AutomationScriptFlow
            key="automation-script"
            sessionName={flowState.sessionName}
            onComplete={handleAutomationScriptComplete}
          />
        )}

        {flowState.currentStep === 'secondary-choice-after-manual' && (
          <ChoiceSection
            key="secondary-choice-after-manual"
            onChoice={(choice: 'manual' | 'automation') =>
              handleSecondaryChoice(
                choice === 'manual' ? 'continue' : 'complete'
              )
            }
            title="What's Next?"
            option1="Generate Automation Scripts"
            option2="Complete Task"
          />
        )}

        {flowState.currentStep === 'secondary-choice-after-automation' && (
          <ChoiceSection
            key="secondary-choice-after-automation"
            onChoice={(choice: 'manual' | 'automation') =>
              handleSecondaryChoice(
                choice === 'manual' ? 'continue' : 'complete'
              )
            }
            title="What's Next?"
            option1="Generate Manual Test Cases"
            option2="Complete Task"
          />
        )}

        {flowState.currentStep === 'complete' && (
          <motion.div
            key="complete"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="min-h-screen flex items-center justify-center"
          >
            <div className="text-center">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{
                  type: 'spring',
                  stiffness: 200,
                  damping: 15,
                }}
                className="mb-8"
              >
                <svg
                  className="w-32 h-32 mx-auto text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </motion.div>
              <motion.h1
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="text-5xl font-bold text-white mb-4"
              >
                Task Completed!
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
                className="text-xl text-gray-400"
              >
                All workflows have been successfully executed.
              </motion.p>
              <motion.button
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.7 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => window.location.href = '/'}
                className="mt-8 px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-lg font-semibold"
              >
                Return to Home
              </motion.button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
