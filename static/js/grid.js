class StockGrid {
  constructor(containerSelector, options = {}) {
    this.container = d3.select(containerSelector);
    this.options = {
      columns: options.columns || 10,
      tileW: options.tileW || 122,
      tileH: options.tileH || 98,
      gap: options.gap || 8,
      onTileClick: options.onTileClick || null
    };

    this.data = [];
    this.tiles = null;
    this.svg = null;
    this.colors = this.readColors();
    this.init();
  }

  readColors() {
    const css = getComputedStyle(document.documentElement);
    return {
      bg: css.getPropertyValue('--surface').trim(),
      line: css.getPropertyValue('--line').trim(),
      ink: css.getPropertyValue('--ink').trim(),
      muted: css.getPropertyValue('--muted').trim(),
      up: css.getPropertyValue('--up').trim(),
      down: css.getPropertyValue('--down').trim(),
      flat: css.getPropertyValue('--flat').trim(),
      accent: css.getPropertyValue('--accent').trim()
    };
  }

  init() {
    this.svg = this.container.append('svg').attr('class', 'stock-grid-svg').attr('preserveAspectRatio', 'xMidYMid meet');
  }

  gridSize(count) {
    const cols = this.options.columns;
    const rows = Math.max(1, Math.ceil(Math.max(count, cols) / cols));
    const width = cols * (this.options.tileW + this.options.gap) - this.options.gap;
    const height = rows * (this.options.tileH + this.options.gap) - this.options.gap;
    return { width, height, rows, cols };
  }

  update(records = []) {
    this.data = records.slice(0, 50);
    const { width, height } = this.gridSize(this.data.length || this.options.columns);
    this.svg.attr('viewBox', `0 0 ${width} ${height}`);

    const tiles = this.svg.selectAll('g.tile').data(this.data, (d) => d.symbol);

    const enter = tiles.enter().append('g').attr('class', 'tile').style('opacity', 0).attr('tabindex', -1);

    enter.append('rect').attr('class', 'tile-bg').attr('rx', 10).attr('ry', 10).attr('width', this.options.tileW).attr('height', this.options.tileH);
    enter.append('rect').attr('class', 'tile-edge').attr('x', 0).attr('y', 0).attr('width', 5).attr('height', this.options.tileH).attr('rx', 8).attr('ry', 8);
    enter.append('text').attr('class', 'tile-symbol').attr('x', 10).attr('y', 24);
    enter.append('text').attr('class', 'tile-price').attr('x', 10).attr('y', 44);
    enter.append('text').attr('class', 'tile-signal').attr('x', this.options.tileW - 10).attr('y', 22).attr('text-anchor', 'end');
    enter.append('rect').attr('class', 'accuracy-track').attr('x', 10).attr('y', this.options.tileH - 16).attr('height', 5).attr('rx', 999).attr('ry', 999).attr('width', this.options.tileW - 20);
    enter.append('rect').attr('class', 'accuracy-fill').attr('x', 10).attr('y', this.options.tileH - 16).attr('height', 5).attr('rx', 999).attr('ry', 999).attr('width', 0);

    const merged = enter.merge(tiles)
      .attr('transform', (d, i) => {
        const col = i % this.options.columns;
        const row = Math.floor(i / this.options.columns);
        const x = col * (this.options.tileW + this.options.gap);
        const y = row * (this.options.tileH + this.options.gap);
        return `translate(${x}, ${y})`;
      });

    merged.select('.tile-bg').attr('fill', this.colors.bg).attr('stroke', this.colors.line).attr('stroke-width', 1.2);
    merged.select('.tile-edge')
      .attr('fill', (d) => this.signalColor(d.prediction))
      .attr('opacity', (d) => Math.max(0.15, +d.confidence || 0.15));

    merged.select('.tile-symbol')
      .attr('fill', this.colors.ink)
      .attr('font-family', 'var(--font-display)')
      .attr('font-size', 14)
      .attr('font-weight', 600)
      .text((d) => d.symbol || '--');

    merged.select('.tile-price')
      .attr('fill', this.colors.muted)
      .attr('font-family', 'var(--font-data)')
      .attr('font-size', 12)
      .text((d) => Number.isFinite(+d.price) ? `$${(+d.price).toFixed(2)}` : '--');

    merged.select('.tile-signal')
      .attr('fill', (d) => this.signalColor(d.prediction))
      .attr('font-family', 'var(--font-data)')
      .attr('font-size', 11)
      .attr('font-weight', 600)
      .text((d) => d.prediction === 'up' ? 'UP' : d.prediction === 'down' ? 'DN' : 'NEU');

    merged.select('.accuracy-track').attr('fill', 'rgba(255,255,255,0.08)');
    merged.select('.accuracy-fill')
      .attr('fill', (d) => {
        if (Number.isFinite(+d.accuracy)) {
          if (+d.accuracy >= 0.7) return this.colors.up;
          if (+d.accuracy >= 0.5) return '#f3b34c';
          return this.colors.down;
        }
        // Not yet evaluated — show confidence as amber placeholder
        return 'rgba(243,179,76,0.45)';
      })
      .transition().duration(420)
      .attr('width', (d) => {
        const val = Number.isFinite(+d.accuracy)
          ? +d.accuracy * 100
          : Number.isFinite(+d.confidence) ? +d.confidence * 100 : 0;
        const pct = Math.max(0, Math.min(100, val));
        return (this.options.tileW - 20) * (pct / 100);
      });

    merged
      .attr('role', 'button')
      .attr('aria-label', (d) => {
        const pred = d.prediction === 'up' ? 'upward' : d.prediction === 'down' ? 'downward' : 'neutral';
        const conf = Number.isFinite(+d.confidence) ? `${Math.round(+d.confidence * 100)} percent confidence` : 'confidence unavailable';
        const price = Number.isFinite(+d.price) ? `$${(+d.price).toFixed(2)}` : 'price unavailable';
        return `${d.symbol || 'unknown stock'}, ${price}, prediction ${pred}, ${conf}`;
      })
      .on('click', (event, d) => this.options.onTileClick && this.options.onTileClick(d))
      .on('keydown', (event, d) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          this.options.onTileClick && this.options.onTileClick(d);
        }
      })
      .on('mouseenter', (event) => d3.select(event.currentTarget).select('.tile-bg').attr('stroke', this.colors.accent).attr('stroke-width', 2))
      .on('mouseleave', (event) => d3.select(event.currentTarget).select('.tile-bg').attr('stroke', this.colors.line).attr('stroke-width', 1.2))
      .on('focusin', (event) => d3.select(event.currentTarget).select('.tile-bg').attr('stroke', this.colors.accent).attr('stroke-width', 2.4))
      .on('focusout', (event) => d3.select(event.currentTarget).select('.tile-bg').attr('stroke', this.colors.line).attr('stroke-width', 1.2));

    enter.transition().duration(300).style('opacity', 1).on('end', function end() { d3.select(this).attr('tabindex', 0); });
    tiles.exit().transition().duration(220).style('opacity', 0).remove();

    this.tiles = merged;
  }

  signalColor(prediction) {
    if (prediction === 'up') return this.colors.up;
    if (prediction === 'down') return this.colors.down;
    return this.colors.flat;
  }

  highlightTile(symbol) {
    if (!this.tiles) return;
    this.tiles.select('.tile-bg')
      .attr('stroke', (d) => d.symbol === symbol ? this.colors.accent : this.colors.line)
      .attr('stroke-width', (d) => d.symbol === symbol ? 2.6 : 1.2);
  }

  patchTile(symbol, patch) {
    if (!this.tiles || !symbol) return;
    const tile = this.tiles.filter((d) => d.symbol === symbol);
    if (tile.empty()) return;

    tile.each(function mutate(d) { Object.assign(d, patch); });

    if (patch.prediction !== undefined || patch.confidence !== undefined) {
      tile.select('.tile-edge')
        .attr('fill', (d) => this.signalColor(d.prediction))
        .attr('opacity', (d) => Math.max(0.15, +d.confidence || 0.15));
      tile.select('.tile-signal').attr('fill', (d) => this.signalColor(d.prediction))
        .text((d) => d.prediction === 'up' ? 'UP' : d.prediction === 'down' ? 'DN' : 'NEU');
      tile.classed('tile-flash', true);
      setTimeout(() => tile.classed('tile-flash', false), 750);
    }

    if (patch.price !== undefined) {
      tile.select('.tile-price').text((d) => Number.isFinite(+d.price) ? `$${(+d.price).toFixed(2)}` : '--');
    }
  }

  destroy() {
    if (this.svg) this.svg.remove();
  }
}

window.StockGrid = StockGrid;
