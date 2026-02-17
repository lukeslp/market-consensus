/**
 * Stock Grid Visualization
 * D3.js v7 - 50 stock tiles with enter/update/exit pattern
 */

class StockGrid {
  constructor(container, options = {}) {
    this.container = d3.select(container);
    this.options = {
      columns: options.columns || 10,
      tileSize: options.tileSize || 120,
      gap: options.gap || 8,
      ...options
    };

    this.colors = {
      up: '#0077bb',     // Blue (colorblind safe)
      down: '#ee7733',   // Orange (colorblind safe)
      flat: '#6b7280',
      background: '#1e293b',
      border: '#334155',
      text: '#e2e8f0',
      textMuted: '#94a3b8'
    };

    this.svg = null;
    this.tiles = null;
    this.init();
  }

  init() {
    const { columns, tileSize, gap } = this.options;
    const rows = 5;
    const width = columns * (tileSize + gap) - gap;
    const height = rows * (tileSize + gap) - gap;

    this.svg = this.container
      .append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .classed('stock-grid', true);
  }

  update(data) {
    const { tileSize, gap } = this.options;

    // Data binding with key function for object constancy
    const tiles = this.svg
      .selectAll('.tile')
      .data(data, d => d.symbol);

    // ENTER: new tiles
    const enter = tiles
      .enter()
      .append('g')
      .attr('class', 'tile')
      .attr('transform', (d, i) => {
        const col = i % this.options.columns;
        const row = Math.floor(i / this.options.columns);
        const x = col * (tileSize + gap);
        const y = row * (tileSize + gap);
        return `translate(${x}, ${y})`;
      })
      .style('opacity', 0);

    // Tile background
    enter
      .append('rect')
      .attr('class', 'tile-bg')
      .attr('width', tileSize)
      .attr('height', tileSize)
      .attr('rx', 8)
      .attr('fill', this.colors.background)
      .attr('stroke', this.colors.border)
      .attr('stroke-width', 1);

    // Symbol text
    enter
      .append('text')
      .attr('class', 'symbol')
      .attr('x', tileSize / 2)
      .attr('y', 30)
      .attr('text-anchor', 'middle')
      .attr('font-size', 18)
      .attr('font-weight', 600)
      .attr('fill', this.colors.text)
      .text(d => d.symbol);

    // Current price
    enter
      .append('text')
      .attr('class', 'price')
      .attr('x', tileSize / 2)
      .attr('y', 55)
      .attr('text-anchor', 'middle')
      .attr('font-size', 14)
      .attr('fill', this.colors.textMuted)
      .text(d => d.price ? `$${d.price.toFixed(2)}` : '--');

    // Change indicator
    enter
      .append('text')
      .attr('class', 'change')
      .attr('x', tileSize / 2)
      .attr('y', 75)
      .attr('text-anchor', 'middle')
      .attr('font-size', 12)
      .attr('font-weight', 500);

    // Prediction badge
    enter
      .append('circle')
      .attr('class', 'prediction-badge')
      .attr('cx', tileSize - 15)
      .attr('cy', 15)
      .attr('r', 8);

    // Prediction icon (arrow)
    enter
      .append('path')
      .attr('class', 'prediction-arrow')
      .attr('transform', `translate(${tileSize - 15}, 15)`)
      .attr('pointer-events', 'none');

    // Accuracy bar background
    enter
      .append('rect')
      .attr('class', 'accuracy-bg')
      .attr('x', 10)
      .attr('y', tileSize - 15)
      .attr('width', tileSize - 20)
      .attr('height', 4)
      .attr('rx', 2)
      .attr('fill', '#334155');

    // Accuracy bar fill
    enter
      .append('rect')
      .attr('class', 'accuracy-fill')
      .attr('x', 10)
      .attr('y', tileSize - 15)
      .attr('height', 4)
      .attr('rx', 2);

    // Enter transition
    enter
      .transition()
      .duration(750)
      .ease(d3.easeCubicOut)
      .style('opacity', 1);

    // UPDATE: existing tiles
    const merged = enter.merge(tiles);

    // Update price
    merged
      .select('.price')
      .transition()
      .duration(500)
      .text(d => d.price ? `$${d.price.toFixed(2)}` : '--');

    // Update change
    merged
      .select('.change')
      .transition()
      .duration(500)
      .text(d => {
        if (!d.change) return '';
        const sign = d.change >= 0 ? '+' : '';
        const pct = (d.change * 100).toFixed(2);
        return `${sign}${pct}%`;
      })
      .attr('fill', d => {
        if (!d.change) return this.colors.flat;
        if (Math.abs(d.change) < 0.001) return this.colors.flat;
        return d.change > 0 ? this.colors.up : this.colors.down;
      });

    // Update prediction badge
    merged
      .select('.prediction-badge')
      .transition()
      .duration(500)
      .attr('fill', d => {
        if (!d.prediction) return this.colors.flat;
        return d.prediction === 'up' ? this.colors.up :
               d.prediction === 'down' ? this.colors.down :
               this.colors.flat;
      });

    // Update prediction arrow (redundant encoding for colorblind users)
    merged
      .select('.prediction-arrow')
      .transition()
      .duration(500)
      .attr('d', d => {
        if (!d.prediction || d.prediction === 'flat') return 'M -3,0 A 3,3 0 1,0 3,0 A 3,3 0 1,0 -3,0'; // Circle
        if (d.prediction === 'up') {
          return 'M 0,-4 L -3,1 L 3,1 Z'; // Up triangle
        } else {
          return 'M 0,4 L -3,-1 L 3,-1 Z'; // Down triangle
        }
      })
      .attr('fill', '#fff')  // White for contrast
      .attr('stroke', 'none');

    // Update accuracy bar
    merged
      .select('.accuracy-fill')
      .transition()
      .duration(750)
      .ease(d3.easeCubicInOut)
      .attr('width', d => {
        if (!d.accuracy) return 0;
        return (tileSize - 20) * (d.accuracy / 100);
      })
      .attr('fill', d => {
        if (!d.accuracy) return this.colors.flat;
        if (d.accuracy >= 70) return this.colors.up;
        if (d.accuracy >= 50) return '#fbbf24'; // Yellow
        return this.colors.down;
      });

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

    // EXIT: removed tiles
    tiles
      .exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();

    this.tiles = merged;
  }

  highlightTile(symbol) {
    this.tiles
      .select('.tile-bg')
      .transition()
      .duration(200)
      .attr('stroke', d => d.symbol === symbol ? '#60a5fa' : '#334155')
      .attr('stroke-width', d => d.symbol === symbol ? 2 : 1);
  }

  destroy() {
    if (this.svg) {
      this.svg.remove();
    }
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = StockGrid;
}
