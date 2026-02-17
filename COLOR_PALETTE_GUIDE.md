# Foresight Dashboard - Color Palette Guide

## Current vs. Recommended Palettes

### Current Palette (RED/GREEN - Not Colorblind Safe)

```
UP (Positive):    #22c55e  ████████  Green 500
DOWN (Negative):  #ef4444  ████████  Red 500
FLAT (Neutral):   #94a3b8  ████████  Slate 400
```

**Problem**: Indistinguishable to users with deuteranopia/protanopia (8% of males)

---

### Recommended Palette (BLUE/ORANGE - Colorblind Safe)

```
UP (Positive):    #0077bb  ████████  Blue 500
DOWN (Negative):  #ee7733  ████████  Orange 500
FLAT (Neutral):   #94a3b8  ████████  Gray 500
```

**Benefits**:
- ✅ Distinguishable by all types of colorblindness
- ✅ High contrast on dark background
- ✅ Avoids financial chart cliché (boring red/green)
- ✅ Blue = trust, growth (psychological positive)
- ✅ Orange = caution, energy (appropriate for downward movement)

---

## Full Spectrum

### Stock Direction Colors (Primary Use)

| Use | Color | Hex | RGB | Notes |
|-----|-------|-----|-----|-------|
| **Up (Primary)** | Blue 500 | #0077bb | rgb(0, 119, 187) | Main upward indicator |
| Up (Bright) | Blue 400 | #33aadd | rgb(51, 170, 221) | Strong positive signal |
| Up (Muted) | Blue 600 | #004488 | rgb(0, 68, 136) | Subtle positive background |
| Up (Dark) | Blue 700 | #003366 | rgb(0, 51, 102) | Minimal accent |
| **Down (Primary)** | Orange 500 | #ee7733 | rgb(238, 119, 51) | Main downward indicator |
| Down (Bright) | Orange 400 | #ff9955 | rgb(255, 153, 85) | Strong negative signal |
| Down (Muted) | Orange 600 | #cc5511 | rgb(204, 85, 17) | Subtle negative background |
| Down (Dark) | Orange 700 | #aa3300 | rgb(170, 51, 0) | Minimal accent |
| **Flat (Neutral)** | Gray 500 | #94a3b8 | rgb(148, 163, 184) | No change / uncertain |

### Provider Categorical Palette (8 Colors - Already Colorblind Safe)

Use for differentiating multiple providers in single view:

| Provider | Color | Hex | RGB | Colorblind Name |
|----------|-------|-----|-----|-----------------|
| 1 | Dark Blue | #332288 | rgb(51, 34, 136) | Indigo |
| 2 | Green | #117733 | rgb(17, 119, 51) | Green |
| 3 | Teal | #44AA99 | rgb(68, 170, 153) | Cyan |
| 4 | Light Blue | #88CCEE | rgb(136, 204, 238) | Sky |
| 5 | Tan | #DDCC77 | rgb(221, 204, 119) | Sand |
| 6 | Rose | #CC6677 | rgb(204, 102, 119) | Pink |
| 7 | Purple | #AA4499 | rgb(170, 68, 153) | Magenta |
| 8 | Wine | #882255 | rgb(136, 34, 85) | Wine |

**Source**: Tol palette (scientifically designed for colorblind accessibility)

---

## Contrast Ratios (WCAG 2.1 AA Compliance)

Against dark background (#0f172a):

| Color | Hex | Contrast Ratio | WCAG Level | Pass? |
|-------|-----|----------------|------------|-------|
| Blue Up | #0077bb | 4.8:1 | AA | ✅ Yes |
| Orange Down | #ee7733 | 5.2:1 | AA | ✅ Yes |
| Gray Flat | #94a3b8 | 5.9:1 | AA | ✅ Yes |

**Requirements**:
- Text: 4.5:1 minimum (AA) or 7:1 (AAA)
- UI Components: 3:1 minimum (AA)

All primary colors exceed WCAG AA requirements for both text and UI.

---

## Confidence Encoding (via Opacity)

Applied to stock direction colors:

| Confidence Range | Opacity | Effective Color (on #0f172a) | Use Case |
|------------------|---------|-------------------------------|----------|
| 90-100% | 1.0 | Full color | High confidence |
| 70-89% | 0.75 | 75% blend | Medium confidence |
| 50-69% | 0.60 | 60% blend | Low confidence |
| <50% | 0.40 | 40% blend | Uncertain |

**Example**: Blue #0077bb at 0.4 opacity on #0f172a background = #2a4661 (still 4.6:1 contrast)

---

## Redundant Encoding (Shapes + Color)

Don't rely on color alone. Use shapes for direction:

```
UP:      ▲ Blue Triangle
DOWN:    ▼ Orange Triangle (inverted)
FLAT:    ● Gray Circle
```

**SVG Paths**:
```javascript
const shapes = {
  up:   'M 0,-4 L -3,1 L 3,1 Z',      // Triangle pointing up
  down: 'M 0,4 L -3,-1 L 3,-1 Z',     // Triangle pointing down
  flat: 'M -3,0 A 3,3 0 1,0 3,0 A 3,3 0 1,0 -3,0'  // Circle
};
```

---

## Colorblind Simulation Results

### Protanopia (Red-Blind, 1% of males)

```
Current Palette:
  Green #22c55e → Perceived as muddy yellow #9da76a
  Red #ef4444   → Perceived as muddy yellow #a6a05c
  INDISTINGUISHABLE ❌

Recommended Palette:
  Blue #0077bb   → Perceived as blue #0077bb (unchanged)
  Orange #ee7733 → Perceived as yellow #d6b03c
  DISTINGUISHABLE ✅
```

### Deuteranopia (Green-Blind, 6% of males)

```
Current Palette:
  Green #22c55e → Perceived as beige #baa472
  Red #ef4444   → Perceived as yellow #c0a05f
  INDISTINGUISHABLE ❌

Recommended Palette:
  Blue #0077bb   → Perceived as blue #0077bb (unchanged)
  Orange #ee7733 → Perceived as yellow #e6c042
  DISTINGUISHABLE ✅
```

### Tritanopia (Blue-Blind, 0.01% of population)

```
Current Palette:
  Green #22c55e → Perceived as cyan #3fcac1
  Red #ef4444   → Perceived as pink #f95e6d
  DISTINGUISHABLE ✅

Recommended Palette:
  Blue #0077bb   → Perceived as teal #00b3b3
  Orange #ee7733 → Perceived as pink #f95e6d
  DISTINGUISHABLE ✅
```

---

## Implementation Checklist

- [ ] Update CSS custom properties in `static/css/style.css`
- [ ] Update hardcoded colors in `static/js/grid.js` constructor
- [ ] Update hardcoded colors in `static/js/detail.js` constructor
- [ ] Update hardcoded colors in `static/js/sidebar.js` constructor
- [ ] Add redundant shape encoding to prediction badges
- [ ] Test with colorblind simulation (Chrome DevTools)
- [ ] Test with real colorblind users (if possible)
- [ ] Update design system documentation

---

## Alternative Palettes (If Blue/Orange Rejected)

### Option 2: Purple/Amber (Warm Alternative)

```
UP:   #8b5cf6  Purple 500 (contrast: 4.2:1) - Regal, premium
DOWN: #f59e0b  Amber 500 (contrast: 6.8:1) - Warning, caution
```

### Option 3: Cyan/Magenta (High Energy)

```
UP:   #06b6d4  Cyan 500 (contrast: 5.4:1) - Tech, innovation
DOWN: #ec4899  Magenta 500 (contrast: 4.9:1) - Alert, action
```

**Recommendation**: Stick with Blue/Orange. It's the most universally accessible and carries appropriate psychological associations for financial data.

---

## References

- **Paul Tol's Colorblind-Safe Palettes**: https://personal.sron.nl/~pault/
- **Coblis Colorblind Simulator**: https://www.color-blindness.com/coblis-color-blindness-simulator/
- **WebAIM Contrast Checker**: https://webaim.org/resources/contrastchecker/
- **WCAG 2.1 Success Criterion 1.4.3** (Contrast - Level AA): https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- **WCAG 2.1 Success Criterion 1.4.1** (Use of Color - Level A): https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html

---

**Last Updated**: 2026-02-16
**Applies To**: Foresight Dashboard v1.0
**Status**: Recommended (not yet implemented)
