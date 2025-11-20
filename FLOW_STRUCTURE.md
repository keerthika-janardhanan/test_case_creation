# Application Flow Structure

## Overview
The application follows a structured flow where users can choose between Manual Test Case generation and Automation Test Script generation. Each path can lead to the other **once**, preventing infinite loops.

## Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                          HOME                                 │
│                     (2 Main Cards)                            │
└────────────┬──────────────────────────────┬──────────────────┘
             │                              │
    ┌────────▼────────┐          ┌─────────▼──────────┐
    │  Design & Execute│          │    Admin Panel     │
    └────────┬────────┘          └────────────────────┘
             │
    ┌────────▼────────────────────────────────────┐
    │         Design & Execute Choice             │
    │         (2 Cards)                           │
    │  • Generate Manual Test Case                │
    │  • Generate Automation Test Script          │
    └──────┬──────────────────────────┬───────────┘
           │                          │
           │                          │
┌──────────▼──────────┐    ┌──────────▼────────────────┐
│  MANUAL PATH        │    │  AUTOMATION PATH          │
│  (First Choice)     │    │  (First Choice)           │
└─────────────────────┘    └───────────────────────────┘
```

## Detailed Flow Paths

### Path 1: Manual First → Automation Second

```
1. HOME
   └─> choice: "Design & Execute"
       └─> manual-test (Generate Manual Test Case)
           └─> manual-success (Shows test cases + Download Excel)
               └─> manual-next-choice (2 Options):
                   ├─> "Complete Task" → COMPLETION (End)
                   └─> "Generate Automation Test Script" →
                       └─> automation-repo-input
                           └─> automation-checking
                               └─> automation-script-choice
                                   ├─> automation-existing-preview → automation-testmanager-upload
                                   └─> automation-refined-preview → automation-generated-script
                                       └─> automation-testmanager-upload
                                           └─> automation-trial-run
                                               └─> automation-completion-choice
                                                   ├─> "Manual Test Case" (SKIPPED - already done)
                                                   └─> "Complete Task" → COMPLETION (End)
```

### Path 2: Automation First → Manual Second

```
1. HOME
   └─> choice: "Design & Execute"
       └─> automation-repo-input (Generate Automation Test Script)
           └─> automation-checking
               └─> automation-script-choice
                   ├─> automation-existing-preview → automation-testmanager-upload
                   └─> automation-refined-preview → automation-generated-script
                       └─> automation-testmanager-upload
                           └─> automation-trial-run
                               └─> automation-completion-choice (2 Options):
                                   ├─> "Complete Task" → COMPLETION (End)
                                   └─> "Generate Manual Test Case" →
                                       └─> manual-test
                                           └─> manual-success
                                               └─> manual-next-choice
                                                   ├─> "Automation Script" (SKIPPED - already done)
                                                   └─> "Complete Task" → COMPLETION (End)
```

## State Management

### completedPaths State
- **Type**: `Set<'manual' | 'automation'>`
- **Purpose**: Track which workflows have been completed
- **Behavior**:
  - When user completes manual path → adds `'manual'` to set
  - When user completes automation path → adds `'automation'` to set
  - On "Return to Home" → reset to empty set

### Flow Control Logic

#### In `handleContinueFromManual()`:
```typescript
// Mark manual as completed
setCompletedPaths(prev => new Set(prev).add('manual'));

// If automation already done, skip choice screen
if (completedPaths.has('automation')) {
  setCurrentStep('completion');  // Go directly to end
} else {
  setCurrentStep('manual-next-choice');  // Show choice screen
}
```

#### In `automation-completion-choice` onClick:
```typescript
// Mark automation as completed
const newCompletedPaths = new Set(completedPaths).add('automation');
setCompletedPaths(newCompletedPaths);

// If manual already done, skip and go to completion
if (completedPaths.has('manual')) {
  setCurrentStep('completion');
} else {
  setSelectedPath('manual');
  setCurrentStep('manual-test');
}
```

## Loop Prevention

### Key Rules:
1. ✅ User can do Manual → Automation (once each)
2. ✅ User can do Automation → Manual (once each)
3. ❌ User **cannot** do Manual → Automation → Manual (loop prevented)
4. ❌ User **cannot** do Automation → Manual → Automation (loop prevented)

### How It Works:
- After completing the **first** workflow, show choice screen with 2 options
- After completing the **second** workflow, automatically go to COMPLETION
- The choice screen is only shown once per session
- Both paths lead to the same final COMPLETION screen

## Completion Screen
- **Message**: "Task Completed! All workflows have been successfully executed."
- **Action**: "Return to Home" button
- **Reset**: Clears all state including `completedPaths`

## Example User Journeys

### Journey 1: Quick Manual-Only
```
Home → Manual Test → Download Excel → Complete Task → End
```

### Journey 2: Quick Automation-Only
```
Home → Automation → Trial Run → Complete Task → End
```

### Journey 3: Full Manual → Automation
```
Home → Manual Test → Download Excel 
     → Choose "Generate Automation" 
     → Automation Flow → Trial Run 
     → Automatically Complete (no choice shown) → End
```

### Journey 4: Full Automation → Manual
```
Home → Automation → Trial Run 
     → Choose "Generate Manual Test Case" 
     → Manual Test Flow → Download Excel 
     → Automatically Complete (no choice shown) → End
```
