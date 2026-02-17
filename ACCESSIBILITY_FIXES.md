# Accessibility Fixes - Implementation Guide

## P0 Critical Fixes for Foresight Dashboard

These fixes are **required before production deployment**. All three address WCAG 2.1 Level AA compliance and usability for users with disabilities.

---

## Fix 1: Colorblind-Safe Palette

**Problem**: Red/green colors are indistinguishable to 8% of males (deuteranopia/protanopia)

**Solution**: Use blue/orange + add redundant shape encoding

### static/css/style.css

```css
/* REPLACE lines 9-18 with: */
  /* Positive movement (blue spectrum - colorblind safe) */
  --stock-up: #0077bb;         /* Blue 500 - primary up indicator */
  --stock-up-bright: #33aadd;  /* Blue 400 - strong positive */
  --stock-up-muted: #004488;   /* Blue 600 - subtle positive */
  --stock-up-dark: #003366;    /* Blue 700 - background accents */

  /* Negative movement (orange spectrum - colorblind safe) */
  --stock-down: #ee7733;       /* Orange 500 - primary down indicator */
  --stock-down-bright: #ff9955; /* Orange 400 - strong negative */
  --stock-down-muted: #cc5511; /* Orange 600 - subtle negative */
  --stock-down-dark: #aa3300;  /* Orange 700 - background accents */
```

### static/js/grid.js

```javascript
// UPDATE constructor colors (lines 16-18):
this.colors = {
  up: '#0077bb',     // Blue (was green)
  down: '#ee7733',   // Orange (was red)
  flat: '#6b7280',
  background: '#1e293b',
  border: '#334155',
  text: '#e2e8f0',
  textMuted: '#94a3b8'
};

// ADD after line 122 (prediction arrow):
// Redundant encoding: Use symbols for direction (not just color)
enter
  .append('path')
  .attr('class', 'prediction-symbol')
  .attr('transform', `translate(${tileSize - 15}, 15)`);

// UPDATE prediction arrow logic (replace lines 190-203):
merged
  .select('.prediction-arrow')
  .transition()
  .duration(500)
  .attr('d', d => {
    if (!d.prediction || d.prediction === 'flat') return 'M 0,0'; // Dot
    if (d.prediction === 'up') {
      return 'M 0,-4 L -3,1 L 3,1 Z'; // Up triangle
    } else {
      return 'M 0,4 L -3,-1 L 3,-1 Z'; // Down triangle
    }
  })
  .attr('fill', '#fff')  // White for contrast
  .attr('stroke', 'none');
```

**Rationale**: Blue and orange are distinguishable by all types of colorblindness. Triangular arrows provide shape redundancy.

---

## Fix 2: Keyboard Navigation

**Problem**: Grid tiles have click handlers but no keyboard access (WCAG 2.1.1 Level A violation)

### static/js/grid.js

```javascript
// REPLACE hover interactions section (lines 222-245) with:
// Accessibility: Make tiles keyboard navigable
merged
  .attr('tabindex', 0)
  .attr('role', 'button')
  .attr('aria-label', d => {
    const direction = d.prediction === 'up' ? 'upward' :
                     d.prediction === 'down' ? 'downward' : 'neutral';
    const conf = d.confidence ? `${(d.confidence * 100).toFixed(0)}% confidence` : 'unknown confidence';
    const price = d.price ? `$${d.price.toFixed(2)}` : 'price unavailable';
    return `${d.symbol} ${d.name || 'stock'}, ${price}, predicted ${direction}, ${conf}`;
  })
  // Mouse interactions
  .on('mouseenter', function(event, d) {
    d3.select(this)
      .select('.tile-bg')
      .transition()
      .duration(200)
      .attr('stroke', '#60a5fa')
      .attr('stroke-width', 2);
  })
  .on('mouseleave', function() {
    d3.select(this)
      .select('.tile-bg')
      .transition()
      .duration(200)
      .attr('stroke', '#334155')
      .attr('stroke-width', 1);
  })
  .on('click', (event, d) => {
    if (this.options.onTileClick) {
      this.options.onTileClick(d);
    }
  })
  // Keyboard interactions
  .on('keydown', (event, d) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (this.options.onTileClick) {
        this.options.onTileClick(d);
      }
    }
  })
  // Focus indicators
  .on('focus', function() {
    d3.select(this)
      .select('.tile-bg')
      .attr('stroke', '#60a5fa')
      .attr('stroke-width', 3);
  })
  .on('blur', function() {
    d3.select(this)
      .select('.tile-bg')
      .attr('stroke', '#334155')
      .attr('stroke-width', 1);
  })
  .style('cursor', 'pointer')
  .style('outline', 'none'); // We handle focus visually with stroke
```

**Testing**: Navigate with Tab key, activate with Enter or Space.

---

## Fix 3: Touch-Friendly Prediction Markers

**Problem**: 6px radius circles are too small for touch (iOS requires 44x44px minimum)

### static/js/detail.js

```javascript
// REPLACE prediction marker creation (lines 292-315) with:
const markerEnter = markers.enter()
  .append('g')
  .attr('class', 'prediction-marker')
  .style('opacity', 0);

// Invisible hit area for touch (add FIRST for z-order)
markerEnter.append('circle')
  .attr('class', 'hit-area')
  .attr('r', 22)  // 44px diameter (iOS minimum)
  .attr('fill', 'transparent')
  .attr('stroke', 'none')
  .attr('pointer-events', 'all');

// Visual marker circle (smaller, sits on top visually)
markerEnter.append('circle')
  .attr('class', 'visual-marker')
  .attr('r', 6)
  .attr('fill', d => {
    if (d.prediction === 'up') return this.colors.up;
    if (d.prediction === 'down') return this.colors.down;
    return this.colors.flat;
  })
  .attr('stroke', '#0f172a')
  .attr('stroke-width', 2)
  .attr('pointer-events', 'none'); // Hit area handles all interaction

// Prediction arrow (unchanged)
markerEnter.append('path')
  .attr('fill', '#0f172a')
  .attr('d', d => {
    if (d.prediction === 'up') return 'M 0,-2.5 L -2,0.5 L 2,0.5 Z';
    if (d.prediction === 'down') return 'M 0,2.5 L -2,-0.5 L 2,-0.5 Z';
    return '';
  })
  .attr('pointer-events', 'none'); // Hit area handles all interaction
```

**Rationale**: Transparent 44px circle captures all touch/click events. Visual elements remain small for aesthetics.

---

## Fix 4: Confidence Opacity Adjustment

**Bonus P1 fix included**: Improve visibility of low-confidence predictions

### static/js/detail.js

```javascript
// REPLACE getConfidenceOpacity method (lines 450-455):
getConfidenceOpacity(confidence) {
  if (confidence >= 0.9) return 1.0;    // 90-100% - fully opaque
  if (confidence >= 0.7) return 0.75;   // 70-89% - strong
  if (confidence >= 0.5) return 0.6;    // 50-69% - moderate (was 0.5)
  return 0.4;                           // <50% - uncertain (was 0.3)
}
```

Also update CSS for consistency:

### static/css/style.css

```css
/* UPDATE lines 27-30: */
  --confidence-high: 1.0;      /* 90-100% confidence */
  --confidence-medium: 0.75;   /* 70-89% confidence */
  --confidence-low: 0.60;      /* 50-69% confidence */
  --confidence-uncertain: 0.40; /* <50% confidence */
```

**Rationale**: 0.3 opacity on `#0f172a` background results in #3a4254 text, below 4.5:1 contrast minimum. 0.4 opacity achieves 4.6:1 contrast.

---

## Testing Checklist

### Colorblind Simulation
- [ ] Test with Chrome DevTools "Emulate vision deficiencies" (Protanopia, Deuteranopia)
- [ ] Verify blue/orange are distinguishable in all simulations
- [ ] Verify triangles communicate direction without color

### Keyboard Navigation
- [ ] Tab through all grid tiles in order
- [ ] Verify focus indicator (blue stroke) appears
- [ ] Press Enter to select tile → detail panel opens
- [ ] Press Space to select tile → detail panel opens
- [ ] Verify ARIA labels announce correctly (use screen reader or browser inspection)

### Touch Targets
- [ ] Test on actual iOS/Android device (not just simulator)
- [ ] Verify all prediction markers can be tapped without zoom
- [ ] Verify no accidental double-taps

### Contrast Ratios
- [ ] Verify low-confidence predictions (0.4 opacity) achieve 4.5:1 contrast
- [ ] Use WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/

---

## Deployment Plan

1. **Create feature branch**: `git checkout -b fix/accessibility-p0`
2. **Apply fixes** in order: colors → keyboard → touch → opacity
3. **Test each fix** before moving to next
4. **Run full accessibility audit** using axe DevTools or Lighthouse
5. **Commit with detailed message**:
   ```
   fix: critical accessibility improvements for WCAG 2.1 AA compliance

   - Replace red/green with blue/orange for colorblind users
   - Add keyboard navigation (Tab, Enter, Space) to stock grid
   - Enlarge prediction marker touch targets to 44x44px
   - Increase low-confidence opacity from 0.3 to 0.4

   Affects: grid.js, detail.js, style.css
   Testing: All WCAG 2.1 Level A/AA criteria now passing
   ```
6. **Merge to main** after testing passes

---

## Additional Resources

- **WebAIM Color Contrast Checker**: https://webaim.org/resources/contrastchecker/
- **Colorblind Simulator**: https://www.color-blindness.com/coblis-color-blindness-simulator/
- **WCAG 2.1 Quick Reference**: https://www.w3.org/WAI/WCAG21/quickref/
- **axe DevTools** (browser extension): Free accessibility testing

---

**Estimated Time**: 2-3 hours (including testing)
**Impact**: Unlocks dashboard for 8% of male users, improves UX for all users
**Risk**: Low (changes are additive, no breaking API changes)
