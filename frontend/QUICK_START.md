# 🚀 Quick Start Guide - New Parallax Frontend

## ✅ What's Been Built

Your new **elegant, professional, dark-themed frontend** with:
- ✨ Horizontal parallax effects
- 🎭 Framer Motion animations
- 🌌 3D particle background (Three.js)
- 🎨 Smooth zoom/fly-away transitions
- 📱 Complete Design workflow
- 🔌 All backend APIs integrated

## 🎯 Access Your New Frontend

### 1. Make sure backend is running:
```powershell
# In terminal 1 (from project root)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start the new frontend:
```powershell
# In terminal 2
cd frontend
npm run dev
```

### 3. Open your browser:
```
http://localhost:5173
```

## 🎬 User Journey

### Step 1: Login
- Navigate to `http://localhost:5173/login`
- Login with your credentials

### Step 2: Homepage
- You'll see two beautiful animated cards:
  - **Design** - Create tests
  - **Execute** - Run tests (placeholder for now)
- 3D particle background animates in the background

### Step 3: Click "Design"
- Smooth transition to Design flow

### Step 4: Recorder
- Enter a session name (e.g., "demo-session")
- Click the floating pulsing **red record button**
- Playwright recorder opens in a new window
- When done, recording auto-ingests to vector DB

### Step 5: Choose Your Path

#### Path A: Manual Test Cases First
1. Click **"Generate Manual Test Cases"**
   - Other option zooms out and disappears
2. Click **"Generate Test Cases"**
   - Processing animation
3. **Download Excel** when ready
4. Choose next step:
   - **Generate Automation Scripts** → continues to automation
   - **Complete Task** → ends workflow

#### Path B: Automation Scripts First
1. Click **"Generate Automation Scripts"**
   - Other option zooms out and disappears
2. Enter **GitHub Details**:
   - Repository Owner (e.g., "mycompany")
   - Repository Name (e.g., "test-automation")
3. Enter **Keyword** to search in repo
4. System checks for existing code
5. Choose:
   - **Use Existing Script** → skip to TestManager upload
   - **Refined Recorder Flow** → continue with preview
6. If Refined Flow:
   - Edit preview in textarea
   - Click **"Looks Good - Continue"**
   - Click **"Generate Payload"**
   - Click **"Confirm & Continue"**
7. **Upload TestManager.xlsx**
   - Drag & drop or click to browse
   - Click **"Persist to Framework"**
8. **Trial Run**
   - Click **"Start Trial Run"**
   - Loading animation while executing
9. **Push to Git**
   - Click **"Push to Git"**
   - Success animation
10. Choose next step:
    - **Generate Manual Test Cases** → manual flow
    - **Complete Task** → ends workflow

### Step 6: Completion
- Beautiful success screen with checkmark
- **"Return to Home"** button

## 🎨 Animation Highlights

Watch for these delightful effects:

1. **Homepage Cards**
   - Hover to see scale + lift effect
   - Glowing border animation
   - Floating particles

2. **Choice Screens**
   - Click one option
   - Other option **zooms out & fades** (parallax!)
   - Selected option scales up with glow pulse

3. **Recorder Button**
   - Pulsing rings while recording
   - Floating particles around it
   - Rotating icon during ingestion

4. **3D Background**
   - 1000 particles in blue/purple gradient
   - Gentle rotation
   - Auto-rotating camera

5. **Page Transitions**
   - Smooth fade + slide animations
   - Spring physics on all interactions

## 🔧 Customization Points

### Change Colors
Edit `frontend/src/components/HomePage.tsx` and other components:
```tsx
// Current: blue-500, purple-500, pink-500
// Change to your brand colors
className="from-blue-600 to-cyan-600"  // Gradients
className="text-purple-400"            // Text colors
className="border-blue-500/30"         // Borders
```

### Adjust Animation Speed
In any component:
```tsx
transition={{ duration: 2 }}  // Slower
transition={{ duration: 0.5 }} // Faster
```

### Particle Count
Edit `frontend/src/components/3d/ParticleField.tsx`:
```tsx
const count = 1000;  // Increase for more particles (impacts performance)
```

## 📝 Testing the Flow

### Quick Test Scenarios

**Test 1: Manual Only**
1. Login → Design → Recorder (session: "test1")
2. Record a simple flow
3. Generate Manual Test Cases
4. Download Excel
5. Complete Task

**Test 2: Automation Only**
1. Login → Design → Recorder (session: "test2")
2. Record a flow
3. Generate Automation Scripts
4. Enter repo: owner="test", repo="demo"
5. Keyword: "login"
6. Choose Refined Flow
7. Edit preview → Generate → Confirm
8. Upload TestManager.xlsx
9. Persist → Trial → Push
10. Complete Task

**Test 3: Both Flows**
1. Login → Design → Recorder (session: "test3")
2. Generate Manual Test Cases first
3. Download Excel
4. Generate Automation Scripts
5. Complete automation flow
6. Complete Task

## 🐛 Troubleshooting

### Issue: 3D particles not showing
- Check browser console for Three.js errors
- Ensure WebGL is supported in your browser
- Try Chrome/Edge (best support)

### Issue: Animations choppy
- Close other tabs
- Check CPU usage
- Reduce particle count in `ParticleField.tsx`

### Issue: "Cannot connect to backend"
- Ensure backend is running on port 8000
- Check CORS settings in FastAPI
- Verify `http://localhost:8000` is accessible

### Issue: Login not working
- Check if you have valid credentials in backend
- Clear browser cache and cookies
- Check network tab in DevTools

## 🎯 Next Steps

1. **Test the complete flow** end-to-end
2. **Customize colors** to match your brand
3. **Add more 3D elements** (optional - can add floating shapes)
4. **Implement Execute flow** (placeholder currently)
5. **Add WebSocket** for real-time updates
6. **Mobile responsive** adjustments

## 📚 Component Reference

| Component | Purpose | Key Props |
|-----------|---------|-----------|
| `HomePage` | Landing page | - |
| `DesignFlow` | Workflow orchestrator | - |
| `RecorderSection` | Recording UI | `onComplete(sessionName)` |
| `ChoiceSection` | Reusable choice screen | `title`, `option1`, `option2`, `onChoice(choice)` |
| `ManualTestCaseFlow` | Manual test generation | `sessionName`, `onComplete()` |
| `AutomationScriptFlow` | Complete automation | `sessionName`, `onComplete()` |
| `Scene3D` | 3D background | - |
| `ParticleField` | Animated particles | - |
| `HorizontalScroll` | GSAP parallax container | `children` |

## 🎨 Color Palette

| Color | Usage | Tailwind Class |
|-------|-------|----------------|
| Blue | Primary actions | `blue-600`, `blue-500` |
| Purple | Automation flow | `purple-600`, `purple-500` |
| Pink | Accents | `pink-500`, `pink-400` |
| Green | Success states | `green-600`, `green-400` |
| Red | Recording | `red-500`, `red-600` |
| Yellow | Trial/Warning | `yellow-600`, `yellow-500` |
| Gray | Background | `gray-900`, `gray-800`, `gray-700` |

## 🚀 Performance Tips

- 3D particles are GPU-accelerated
- Framer Motion uses transform/opacity (performant)
- Code-split with dynamic imports if bundle gets too large
- Images should be optimized (currently using SVG icons)

---

**Enjoy your new elegant frontend!** 🎉

If you have questions or want to customize further, check:
- `frontend/NEW_FRONTEND_README.md` - Technical details
- Individual component files for implementation
- Framer Motion docs: https://www.framer.com/motion/
- Three.js docs: https://threejs.org/
