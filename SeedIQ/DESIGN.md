---
name: SeedIQ
colors:
  surface: '#111415'
  surface-dim: '#111415'
  surface-bright: '#373a3b'
  surface-container-lowest: '#0c0f10'
  surface-container-low: '#191c1d'
  surface-container: '#1d2021'
  surface-container-high: '#282a2b'
  surface-container-highest: '#323536'
  on-surface: '#e1e3e4'
  on-surface-variant: '#d0c5af'
  inverse-surface: '#e1e3e4'
  inverse-on-surface: '#2e3132'
  outline: '#99907c'
  outline-variant: '#4d4635'
  surface-tint: '#e9c349'
  primary: '#d4af37'
  on-primary: '#3c2f00'
  primary-container: '#d4af37'
  on-primary-container: '#554300'
  inverse-primary: '#735c00'
  primary-fixed: '#ffe088'
  primary-fixed-dim: '#e9c349'
  on-primary-fixed: '#241a00'
  on-primary-fixed-variant: '#574500'
  secondary: '#a0d1b8'
  on-secondary: '#033826'
  secondary-container: '#22513e'
  on-secondary-container: '#92c3aa'
  secondary-fixed: '#bbeed3'
  secondary-fixed-dim: '#a0d1b8'
  on-secondary-fixed: '#002114'
  on-secondary-fixed-variant: '#204f3c'
  emerald-forest: '#043927'
  tertiary: '#ceced1'
  on-tertiary: '#2f3133'
  tertiary-container: '#b2b3b5'
  on-tertiary-container: '#444547'
  tertiary-fixed: '#e2e2e5'
  tertiary-fixed-dim: '#c6c6c9'
  on-tertiary-fixed: '#1a1c1e'
  on-tertiary-fixed-variant: '#454749'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  background: '#111415'
  on-background: '#e1e3e4'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 64px
    fontWeight: '700'
    lineHeight: '72px'
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 40px
    fontWeight: '700'
    lineHeight: '48px'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '40px'
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '32px'
  body-lg:
    fontFamily: Outfit
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '28px'
  body-md:
    fontFamily: Outfit
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '24px'
  accent-quote:
    fontFamily: Instrument Serif
    fontSize: 28px
    fontWeight: '400'
    lineHeight: '36px'
    fontStyle: italic
  label-sm:
    fontFamily: Outfit
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '16px'
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.125rem
  lg: 0.25rem
  xl: 0.5rem
  full: 0.75rem
spacing:
  unit: 8px
  margin-desktop: 64px
  margin-mobile: 16px
  gutter: 24px
  container-max: 1440px
---

# 🌾 SeedIQ Design System & Frontend Specifications (Private Agricultural Intelligence)

Welcome to the **SeedIQ** Design Specification. This document outlines the exact user experience, styling principles, layout structure, color schemes, and page requirements for the SeedIQ platform to enable Google Stitch to perfectly build or style the screens.

---

## 🎨 Theme & Brand Archetype
SeedIQ is a **Private Agricultural Decision-Support System** that fuses classical Machine Learning models with cutting-edge Qiskit/PennyLane Quantum Neural Networks. 

- **Aesthetic Style:** Premium Satin-Glass & Champagne Gold Dark Mode. It utilizes deep graphite bases, glowing gold/emerald borders, and satin translucent glass elements that float above a subtle, gold-dusted ambient space.
- **Tone:** Technical, authoritative, futuristic, yet extremely premium, editorial, and clean.
- **Key Visual Elements:**
  - **Gold Dust Overlay:** Floating gold points rendering in the background (`background: radial-gradient(circle at 50% 50%, rgba(212, 175, 55, 0.03) 0%, transparent 70%)`).
  - **Satin Glass Cards:** Frosted surfaces featuring `rgba(255, 255, 255, 0.02)` fill, `24px` backdrop-blur, a thin `1px solid rgba(212, 175, 55, 0.15)` champagne-gold border, and soft black shadows.
  - **Champagne Glow:** Ambient shadow glows using gold light maps (`box-shadow: 0 0 30px rgba(212, 175, 55, 0.15)`).

---

## 🎨 Design Colors
This design system operates exclusively in dark-mode to maximize readability of quantum charts and status logs.

- **Background & Canvas:** `#111415` (Deep dark graphite/obsidian)
- **Champagne Gold (Primary Accent):** `#d4af37` (Represents premium quality, precision, and harvest value)
- **Emerald Forest (Secondary Accent):** `#043927` (Represents deep vegetation, foliage growth, and agricultural success)
- **Sage Mint (Data Highlight Accent):** `#a0d1b8` (Used for charts, positive status indicators, and viability badges)
- **Satin Glass Card Fills:** `rgba(255, 255, 255, 0.02)` with `rgba(212, 175, 55, 0.15)` gold borders.
- **Subtle Muted Text (On-surface-variant):** `#d0c5af` for labels and secondary details.
- **Main Accent Text (On-surface):** `#e1e3e4` for headings, parameters, and emphasis.

---

## ✍️ Typography & Hierarchies
We use three premium Google Fonts:
1. **Space Grotesk** (Display/Headlines): Highly technical, geometric sans-serif that looks exceptional for branding, navbars, and metrics.
2. **Outfit** (Body/Labels): A beautifully soft, rounded sans-serif font that is exceptionally readable for inputs, charts, and content body blocks.
3. **Instrument Serif** (Accent Quotes): High-end italic serif used for editorial callouts, quotes, and conceptual commentary.

- **Display Headings:** Space Grotesk, Bold, letter-spacing `-0.02em`.
- **Accent Editorial Quotes:** Instrument Serif, Italic, 28px.
- **Body & Forms:** Outfit, Medium-Regular, high line-height (`1.6`) for reading comfort.
- **Icons:** Material Symbols Outlined (Fine line, 100-200 weight).

---

## 🗂️ Global Component Layouts

### 1. The Satin Glass Navigation Bar (Sticky-Top)
- **Brand Identity:** Gradient brand logo showing `🌱 SeedIQ` in Space Grotesk.
- **Navigation Links:** `Dashboard`, `Crop AI`, `Yield AI`, `Seed AI`, `Storage`, `Quantum`, `Upload`, and `Logout` (styled in warning red).
- **Behavior:** Semi-translucent graphite fill (`rgba(17, 20, 21, 0.8)`) with backdrop-blur (`24px`) and a thin brass border (`border-outline-variant/10`) at the bottom.

### 2. Form Inputs & Control Blocks
- **Inputs & Selects:** Dark translucent panels (`rgba(0, 0, 0, 0.45)`) with thin brass borders. On focus, they glow with `box-shadow: 0 0 15px rgba(212, 175, 55, 0.25)` and border-color `#d4af37`.
- **Labels:** Muted champagne-gray, set above the input fields.

### 3. Custom Action Buttons
- **Primary Gold Button:** Solid gold background (`#d4af37`) with dark on-primary text (`#3c2f00`). Scales slightly on hover (`1.03`) with a champagne glow.
- **Secondary Ghost Button:** A thin gold border (`border-primary/30`) with a very subtle translucent background. On hover, the fill becomes more solid with a upward hover transition.

---

## 🖥️ Screen-by-Screen Specifications & Prompts

### Screen 1: Dashboard (`/dashboard`)
*The central control hub summarizing model accuracy and actions.*
- **Core Widgets:**
  - **Consensus Accuracy Panel:** A circular meter showing 96% Ensemble model accuracy.
  - **Base Model Performance Cards:**
    - Random Forest Crop Classifier: `92%` Accuracy.
    - XGBoost Yield Regressor: `94%` R² Score.
    - Support Vector Machine Seed Classifier: `89%` Accuracy.
  - **Quick Action Links:** Four grid cards redirecting to Crop AI, Yield AI, Seed AI, and Quantum Explainer.
  - **Data Upload Center:** A drag-and-drop widget for CSV file analysis.

### Screen 2: Crop AI Recommendation (`/crop-recommendation`)
*A soil chemistry input form that recommends optimal crops using unified classical/quantum prediction voting.*
- **Inputs Needed:**
  - Nitrogen content (N) (kg/ha)
  - Phosphorus content (P) (kg/ha)
  - Potassium content (K) (kg/ha)
  - Soil pH (0-14 slider)
  - Temperature (°C)
  - Humidity (%)
  - Rainfall (mm)
- **Output View:**
  - Shows 3 distinct prediction panels: **Classical (Random Forest)**, **Quantum (VQC)**, and the **Ensemble Recommendation** (e.g. Rice, Maize, Wheat).
  - Glowing badges: Sage Mint badge for Quantum (`#a0d1b8`) and Gold badge for Classical (`#d4af37`).

### Screen 3: Yield AI Prediction (`/yield-prediction`)
*A crop production forecasting form.*
- **Inputs Needed:**
  - Crop Selector (Dropdown: Rice, Wheat, Maize, Sugarcane, Cotton)
  - Season Selector (Dropdown: Kharif, Rabi, Summer, Whole Year)
  - Area Input (Hectares)
- **Output View:**
  - Calculates predicted yield (Tonnes) for Classical, Quantum, and Ensemble.
  - Includes a mock prediction summary card showing average yield per hectare.

### Screen 4: Seed Viability Analyzer (`/seed-viability`)
*Checks whether seed batches are viable for planting based on physical attributes.*
- **Inputs Needed:**
  - Seed Moisture Content (%)
  - Seed Weight (grams per 100 seeds)
- **Output View:**
  - Unified prediction results: **Viable** (in bright sage mint green) or **Non-Viable** (in red container).
  - Displays a details card listing environmental parameters to maintain seed viability.

### Screen 5: Storage Preservation recommendation (`/storage-recommendation`)
*Provides guidelines for preserving harvested crops.*
- **Inputs Needed:**
  - Crop Selection Dropdown (Rice, Wheat, Maize, Sugarcane, Cotton)
- **Output View:**
  - Displays specific temperature, humidity, and preservation directives:
    - *Rice:* 15-20°C, 60% Humidity, fumigation recommended.
    - *Wheat:* 15-18°C, 50-60% Humidity, silo storage.
    - *Sugarcane:* 12-16°C, 85-90% Humidity, controlled atmosphere storage.

### Screen 6: Quantum Explainer & Playground (`/quantum-ml`)
*An educational screen with interactive simulations representing VQC quantum states.*
- **Interface Layout:**
  - Split-screen layout.
  - **Left Side:** Input controls mirroring the Crop, Yield, and Seed fields for a live simulation run.
  - **Right Side:** Visualizations detailing the Quantum Circuit (Ansatz, RX/RY/RZ gates, entanglement lines, expectation measurements on Z-axis).
  - **Stacked Meta-Model Consensus Output:** Displays a probability score (e.g., 85.5% probability of success) with a concluding status label ("Optimal Performance").

---

## 🚀 Prompt for Google Stitch Screen Generation

Copy the prompt below to generate a new screen matching the SeedIQ design language inside Google Stitch:

```text
Generate a responsive web screen for SeedIQ (a private agricultural decision intelligence platform).
Theme style is Premium Satin-Glass & Champagne Gold Dark Mode:
- Base Background: Deep dark graphite/obsidian (#111415)
- Accents: Champagne Gold (#d4af37) and Emerald Forest (#043927) or Sage Mint (#a0d1b8)
- Fonts: Headline in Space Grotesk, body in Outfit, editorial quotes in Instrument Serif italic.
- Elements: Satin glass cards (background: rgba(255,255,255,0.02) with 24px backdrop-blur and 1px border of rgba(212,175,55,0.15) gold, casting a champagne shadow).
- Gold Dust Backdrop: Radial gradient space with gold dust flecks (rgba(212,175,55,0.03)).
- Forms: Form inputs should have dark translucent background fields, with a brass/gold focus outline and subtle gold glow.
- Layout: Modern grid containing KPI metrics, soil input parameters, and prediction result panels.
[Insert screen-specific inputs/outputs here, such as: "Create the Soil Crop Recommendation Screen with inputs for N, P, K, pH, Temperature, Humidity, and Rainfall, and output badges for Classical RF prediction, Quantum VQC prediction, and Stacked Ensemble Decision."]
```
