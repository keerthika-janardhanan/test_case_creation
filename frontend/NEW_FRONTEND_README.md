# New Parallax Frontend - Design Flow

## 🎨 Overview

An elegant, professional dark-themed frontend with horizontal parallax effects, 3D animated elements, and smooth transitions. Built with React, Framer Motion, Three.js, and GSAP.

## 🚀 Tech Stack

- **React 18** + TypeScript
- **Framer Motion** - Advanced animations & transitions
- **Three.js** + **@react-three/fiber** - 3D particle background
- **@react-three/drei** - Three.js helpers
- **GSAP** (GreenSock) - ScrollTrigger for horizontal parallax
- **Tailwind CSS** - Dark theme styling
- **Vite** - Build tool

## 📁 New File Structure

```
frontend/src/
├── components/
│   ├── HomePage.tsx                    # Landing page with Design/Execute options
│   ├── 3d/
│   │   ├── Scene3D.tsx                 # 3D canvas wrapper
│   │   ├── ParticleField.tsx           # Animated particle background
│   │   └── index.ts
│   ├── parallax/
│   │   ├── HorizontalScroll.tsx        # GSAP horizontal scroll container
│   │   └── index.ts
│   └── design-flow/
│       ├── DesignFlow.tsx              # Main orchestrator for design workflow
│       ├── RecorderSection.tsx         # Floating recorder button & flow
│       ├── ChoiceSection.tsx           # Reusable choice screen with zoom effects
│       ├── ManualTestCaseFlow.tsx      # Manual test case generation UI
│       ├── AutomationScriptFlow.tsx    # Complete automation workflow
│       └── index.ts
└── App.tsx                             # Updated routing with new pages
```

## 🎯 User Flow

### Homepage (`/` or `/home`)
- Two animated cards: **Design** and **Execute**
- 3D particle background
- Smooth hover effects with glow animations

### Design Flow (`/design`)

#### 1️⃣ **Recorder Section**
- Floating, pulsing record button
- User enters session name
- Triggers Playwright recorder (opens new window)
- Auto-ingests to vector DB after recording

#### 2️⃣ **Choice Screen**
- Two options appear:
  - Generate Manual Test Cases
  - Generate Automation Scripts
- Selected option stays, other **zooms out & disappears** (parallax effect)

#### 3️⃣ **Manual Test Case Flow** (if selected)
1. Generate test cases from recording
2. Download Excel file
3. Show secondary choice:
   - Generate Automation Scripts → continue to automation flow
   - Complete Task → end workflow

#### 4️⃣ **Automation Script Flow** (if selected)
1. **GitHub Repo Details** - Enter owner/repo
2. **Keyword Input** - Search term for existing code
3. **Check Repository** - Loading state while searching
4. **Show Existing vs Refined**
   - Display existing code (if found)
   - Display refined recorder flow
   - User chooses which path
5. **If Refined Flow Selected**:
   - Editable preview textarea
   - Generate payload
   - Confirm script
6. **TestManager Upload** - Upload Excel file
7. **Persist** - Save to internal framework
8. **Trial Run** - Execute test
9. **Push to Git** - Commit & push to repo
10. **Complete** - Show success & offer next steps

## 🎨 Animation Features

### Framer Motion Effects
- **Page Transitions**: Smooth fade + slide animations
- **Card Hover**: Scale up, lift with shadow
- **Zoom Out Effect**: Unselected options gracefully disappear
- **Spring Physics**: Natural bounce on interactions
- **Stagger Children**: Sequential reveal of elements

### 3D Background (Three.js)
- **1000 particles** in blue/purple gradient
- Gentle rotation and floating motion
- Additive blending for glow effect
- Auto-rotating orbit camera
- Fixed position behind all content

### GSAP Parallax (Future Enhancement)
- `HorizontalScroll.tsx` ready for horizontal scrolling
- Can be applied to multi-panel workflows

## 🔌 Backend Integration

All API calls use existing FastAPI endpoints at `http://localhost:8000`:

| Endpoint | Purpose |
|----------|---------|
| `POST /api/recorder/start` | Start Playwright recording |
| `POST /api/ingest/recordings` | Ingest recording to vector DB |
| `POST /api/manual-test-cases/generate` | Generate Excel test cases |
| `POST /api/automation/check-existing` | Check repo for existing code |
| `POST /api/automation/generate-payload` | Generate script payload |
| `POST /api/automation/persist` | Persist to framework |
| `POST /api/automation/trial` | Run trial test |
| `POST /api/automation/push` | Push to GitHub |

**Note**: Backend remains unchanged - only frontend is new.

## 🎯 Routes

| Path | Description |
|------|-------------|
| `/` or `/home` | New animated homepage |
| `/design` | Complete design workflow |
| `/execute` | Placeholder for future execution flow |
| `/dashboard` | Original dashboard (still accessible) |
| `/login` | Login page |

## 🎨 Design Principles

1. **Professional Dark Theme**
   - Gradient backgrounds: gray-900 → slate-900 → black
   - Accent colors: Blue, Purple, Pink gradients
   - Glassmorphism: backdrop-blur effects

2. **Smooth Animations**
   - All transitions use spring physics
   - Loading states with spinners
   - Floating particle decorations

3. **Clear Visual Hierarchy**
   - Large, bold typography (text-4xl to text-6xl)
   - Generous spacing and padding
   - Glowing borders and shadows on interactive elements

4. **Motion Graphics**
   - Pulsing rings on active states
   - Floating particles on all major screens
   - Scale + rotation on hover
   - Smooth page transitions with AnimatePresence

## 🚀 Running the Frontend

```powershell
# Navigate to frontend directory
cd frontend

# Install dependencies (already done)
npm install

# Start dev server
npm run dev
```

Frontend runs on: **http://localhost:5173**
Backend API runs on: **http://localhost:8000**

## 🔄 State Management

Each flow component manages its own state:

- **DesignFlow**: Orchestrates overall workflow steps
- **RecorderSection**: Recording + ingestion status
- **AutomationScriptFlow**: Complex multi-step automation state
- **ManualTestCaseFlow**: Generation + download status

No global state management needed - component-level state is sufficient.

## 🎭 Animation Libraries Used

### Framer Motion
```tsx
<motion.div
  initial={{ opacity: 0, scale: 0.8 }}
  animate={{ opacity: 1, scale: 1 }}
  exit={{ opacity: 0, scale: 0.8 }}
  whileHover={{ scale: 1.05, y: -10 }}
>
```

### GSAP ScrollTrigger
```tsx
gsap.timeline({
  scrollTrigger: {
    trigger: container,
    scrub: 1,
    pin: true,
  },
})
```

### Three.js (via @react-three/fiber)
```tsx
<Canvas>
  <ParticleField />
  <OrbitControls autoRotate />
</Canvas>
```

## 🌟 Key Features

✅ **Horizontal Parallax** - Ready for implementation  
✅ **3D Particle Background** - Subtle, professional  
✅ **Zoom/Fly-away Effects** - Smooth choice transitions  
✅ **Floating Recorder Button** - Pulsing animations  
✅ **Editable Preview** - Textarea for user feedback  
✅ **Multi-step Automation Flow** - Complete GitHub integration  
✅ **Dark Professional Theme** - Elegant gradients  
✅ **Spring Physics** - Natural motion  
✅ **Loading States** - Spinners & progress indicators  
✅ **Backend Integration** - All existing APIs connected  

## 🔮 Future Enhancements

1. **True Horizontal Scrolling** - Use HorizontalScroll component for panel-based navigation
2. **Execute Flow** - Build out the execution workflow
3. **Real-time Updates** - WebSocket integration for live status
4. **More 3D Elements** - Interactive shapes, not just particles
5. **Mobile Responsive** - Touch-friendly parallax
6. **Dark/Light Toggle** - User preference (currently dark only)

## 📝 Notes

- All existing functionality preserved
- Backend APIs remain unchanged
- Original Dashboard still accessible at `/dashboard`
- 3D background is lightweight (~1000 particles)
- Animations are GPU-accelerated for smooth performance
- TypeScript strict mode enabled

---

**Built with ❤️ for an elegant, professional test automation experience**
