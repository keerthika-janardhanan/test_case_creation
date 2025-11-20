# 🎨 UI Design Preview

## Color Palette

### Primary Colors
```
Primary Green:     HSL(142.1, 76.2%, 36.3%)  #22c55e
Secondary Gray:    HSL(240, 4.8%, 95.9%)     #f5f5f5
Accent Purple:     #a855f7
Accent Pink:       #d946ef
```

### Semantic Colors
```
Success:   Green    #22c55e
Warning:   Yellow   #f59e0b
Error:     Red      #ef4444
Info:      Blue     #3b82f6
```

## Component Styles

### Cards
```
Background:     White (#ffffff)
Border:         1px solid hsl(240, 5.9%, 90%)
Border Radius:  12px (rounded-xl)
Shadow:         0 1px 3px 0 rgba(0, 0, 0, 0.1)
Padding:        24px (p-6)
```

### Buttons

#### Default (Primary)
```
Background:     Green (#22c55e)
Text:           White
Hover:          Lighter green
Height:         36px (h-9)
Padding:        16px horizontal
Border Radius:  6px (rounded-md)
```

#### Outline
```
Background:     Transparent
Border:         1px solid hsl(240, 5.9%, 90%)
Text:           Foreground color
Hover:          Light gray background
```

#### Ghost
```
Background:     Transparent
Text:           Foreground color
Hover:          Light accent background
```

### Badges
```
Background:     Primary color
Text:           White
Padding:        2.5px 10px
Border Radius:  6px (rounded-md)
Font Size:      12px
Font Weight:    600 (semibold)
```

### Sidebar Navigation
```
Width (Desktop):    264px
Background:         Card color (white)
Border:             1px solid border color (right)
Item Height:        40px
Active Item:        Primary background
Inactive Item:      Muted foreground
Hover:              Accent background
Icon Size:          20px
```

## Layout Structure

### Desktop (> 1024px)
```
┌─────────────────────────────────────────────┐
│ Sidebar (264px)  │  Main Content            │
│                  │                           │
│  Logo            │  Header                   │
│                  │                           │
│  Navigation      │  ┌─────────────────────┐ │
│  - Home          │  │     Stats Cards     │ │
│  - Recorder      │  │  (Grid 2x2 or 4x1)  │ │
│  - Tests         │  └─────────────────────┘ │
│  - ...           │                           │
│                  │  ┌─────────────────────┐ │
│  User Info       │  │   Main Content      │ │
│  Logout          │  │   (Cards, Forms)    │ │
│                  │  └─────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Mobile (< 768px)
```
┌─────────────────────────────┐
│ ☰  Test Automation Studio   │ ← Mobile Header
├─────────────────────────────┤
│                             │
│  ┌───────────────────────┐  │
│  │    Stats Cards        │  │
│  │    (Stacked)          │  │
│  └───────────────────────┘  │
│                             │
│  ┌───────────────────────┐  │
│  │   Main Content        │  │
│  │   (Full Width)        │  │
│  └───────────────────────┘  │
│                             │
└─────────────────────────────┘

Sidebar opens as overlay when ☰ clicked
```

## Typography

### Headings
```
H1:  text-4xl (36px) font-bold
H2:  text-3xl (30px) font-bold
H3:  text-2xl (24px) font-semibold
H4:  text-xl (20px) font-semibold
H5:  text-lg (18px) font-medium
```

### Body Text
```
Large:   text-lg (18px)
Default: text-base (16px)
Small:   text-sm (14px)
XSmall:  text-xs (12px)
```

### Font Weights
```
Bold:       700
Semibold:   600
Medium:     500
Regular:    400
```

## Spacing

### Container Spacing
```
Max Width:     1280px (max-w-7xl)
Padding:       32px (px-8)
Gap:           32px (space-y-8)
```

### Card Spacing
```
Padding:       24px (p-6)
Header Gap:    6px (space-y-1.5)
Content Gap:   16px (space-y-4)
```

### Grid Spacing
```
Gap:           16px (gap-4) or 24px (gap-6)
Columns:       2-4 based on screen size
```

## Animation

### Transitions
```
Duration:      200-300ms
Easing:        ease-out
Properties:    colors, transform, opacity
```

### Hover Effects
```
Transform:     translateY(-4px) on cards
Shadow:        Increase on hover
Color:         Lighten/darken 10%
```

### Page Transitions
```
Initial:       opacity: 0, y: -20
Animate:       opacity: 1, y: 0
Duration:      0.5s
Delay:         Stagger by 0.1s
```

## Shadows

### Default
```
sm:   0 1px 2px 0 rgba(0, 0, 0, 0.05)
md:   0 4px 6px -1px rgba(0, 0, 0, 0.1)
lg:   0 10px 15px -3px rgba(0, 0, 0, 0.1)
```

### Elevated (Hover)
```
xl:   0 20px 25px -5px rgba(0, 0, 0, 0.1)
```

## Iconography

### Icon Sizes
```
Small:   16px (h-4 w-4)
Default: 20px (h-5 w-5)
Large:   24px (h-6 w-6)
XLarge:  32px (h-8 w-8)
```

### Icon Colors
```
Primary:    Current text color
Muted:      text-muted-foreground
Accent:     Primary color
```

## Form Elements

### Input Fields
```
Height:         40px (h-10)
Padding:        8px 12px
Border:         1px solid hsl(240, 5.9%, 90%)
Border Radius:  6px (rounded-md)
Focus:          Ring color (2px)
Font Size:      14px
```

### Labels
```
Font Size:      14px (text-sm)
Font Weight:    500 (medium)
Margin Bottom:  8px (mb-2)
Color:          Foreground
```

## Responsive Breakpoints

```css
/* Mobile First Approach */
sm:  640px   /* Small tablets */
md:  768px   /* Tablets */
lg:  1024px  /* Small laptops */
xl:  1280px  /* Desktops */
2xl: 1400px  /* Large screens */

/* Usage Examples */
.grid-cols-1        /* Mobile: 1 column */
.md:grid-cols-2     /* Tablet: 2 columns */
.lg:grid-cols-3     /* Desktop: 3 columns */
.xl:grid-cols-4     /* Large: 4 columns */
```

## Dark Mode (Ready to Enable)

### Background Colors
```
Background:     hsl(20, 14.3%, 4.1%)   #1a1310
Card:           hsl(24, 9.8%, 10%)     #1c1917
Popover:        hsl(0, 0%, 9%)         #171717
```

### Text Colors
```
Foreground:     hsl(0, 0%, 95%)        #f2f2f2
Muted:          hsl(240, 5%, 64.9%)    #9ca3af
```

### Primary Colors (Dark Mode)
```
Primary:        hsl(142.1, 70.6%, 45.3%)  Lighter green
Primary FG:     hsl(144.9, 80.4%, 10%)    Dark green
```

## Example Component Compositions

### Stats Card
```tsx
<Card>
  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
    <CardTitle className="text-sm font-medium">
      Total Users
    </CardTitle>
    <Users className="h-4 w-4 text-muted-foreground" />
  </CardHeader>
  <CardContent>
    <div className="text-2xl font-bold">1,234</div>
    <p className="text-xs text-muted-foreground">
      +20% from last month
    </p>
  </CardContent>
</Card>
```

### Feature Card with Gradient Icon
```tsx
<Card className="hover:shadow-lg transition-all hover:-translate-y-1">
  <CardHeader>
    <div className="p-3 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500">
      <Icon className="h-6 w-6 text-white" />
    </div>
    <CardTitle className="mt-4">Feature Name</CardTitle>
    <CardDescription>Description text</CardDescription>
  </CardHeader>
  <CardContent>
    <Button variant="ghost" className="w-full">
      Learn More
    </Button>
  </CardContent>
</Card>
```

### Gradient Heading
```tsx
<h1 className="text-4xl font-bold bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent">
  Beautiful Heading
</h1>
```

---

## Visual Design Principles

1. **Consistency** - Use design tokens (CSS variables) throughout
2. **Hierarchy** - Clear visual hierarchy with size, weight, color
3. **Whitespace** - Generous spacing for breathing room
4. **Contrast** - Sufficient contrast for accessibility (WCAG AA)
5. **Responsiveness** - Mobile-first, progressive enhancement
6. **Motion** - Subtle, purposeful animations
7. **Color** - Limited palette, semantic colors
8. **Typography** - Clear, readable, hierarchical

---

**This design system creates a modern, professional, and accessible user interface! ✨**
