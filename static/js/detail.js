/**
 * Stock Detail Visualization
 * D3.js v7 - Individual stock view with prediction timeline and accuracy chart
 */

class StockDetail {
  constructor(container, options = {}) {
    this.container = d3.select(container);
    this.options = {
      width: options.width || 800,
      height: options.height || 400,
      margin: { top: 40, right: 60, bottom: 60, left: 60 },
      ...options
    };

    this.colors = {
      up: getComputedStyle(document.documentElement).getPropertyValue('--stock-up').trim(),
      down: getComputedStyle(document.documentElement).getPropertyValue('--stock-down').trim(),
      flat: getComputedStyle(document.documentElement).getPropertyValue('--stock-flat').trim(),
      background: getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary').trim(),
      text: getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim(),
      textMuted: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim(),
      glassBorder: 'rgba(255, 255, 255, 0.1)'
    };

    this.svg = null;
    this.chart = null;
    this.scales = {};
    this.currentStock = null;
    this.init();
  }

  init() {
    const { width, height, margin } = this.options;
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    this.svg = this.container
      .append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .attr('role', 'img')
      .attr('aria-label', 'Stock prediction timeline chart')
      .classed('stock-detail', true);

    // Chart group
    this.chart = this.svg
      .append('g')
      .attr('transform', `translate(${margin.left}, ${margin.top})`);

    // Clip path for animations
    this.svg
      .append('defs')
      .append('clipPath')
      .attr('id', 'chart-clip')
      .append('rect')
      .attr('width', chartWidth)
      .attr('height', chartHeight);

    // Grid lines container
    this.chart.append('g').attr('class', 'grid grid-y');
    this.chart.append('g').attr('class', 'grid grid-x');

    // Data containers
    this.chart.append('g').attr('class', 'price-area').attr('clip-path', 'url(#chart-clip)');
    this.chart.append('g').attr('class', 'price-line').attr('clip-path', 'url(#chart-clip)');
    this.chart.append('g').attr('class', 'predictions').attr('clip-path', 'url(#chart-clip)');
    this.chart.append('g').attr('class', 'confidence-bands').attr('clip-path', 'url(#chart-clip)');

    // Axes
    this.chart.append('g').attr('class', 'axis axis-x');
    this.chart.append('g').attr('class', 'axis axis-y');

    // Tooltip
    this.tooltip = this.container
      .append('div')
      .attr('class', 'detail-tooltip')
      .style('position', 'absolute')
      .style('opacity', 0)
      .style('background', 'rgba(15, 23, 42, 0.95)')
      .style('border', '1px solid rgba(255, 255, 255, 0.2)')
      .style('border-radius', '8px')
      .style('padding', '12px')
      .style('pointer-events', 'none')
      .style('font-size', '13px')
      .style('color', this.colors.text)
      .style('backdrop-filter', 'blur(10px)');
  }

  update(stockData) {
    if (!stockData || !stockData.history || stockData.history.length === 0) {
      this.showEmpty();
      return;
    }

    this.currentStock = stockData;
    const { width, height, margin } = this.options;
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    // Parse dates
    const parseDate = d3.timeParse('%Y-%m-%d');
    stockData.history.forEach(d => {
      d.date = parseDate(d.date);
      d.price = +d.price;
    });

    if (stockData.predictions) {
      stockData.predictions.forEach(d => {
        d.date = parseDate(d.date);
        d.confidence = +d.confidence;
      });
    }

    // Scales
    const xExtent = d3.extent(stockData.history, d => d.date);
    this.scales.x = d3.scaleTime()
      .domain(xExtent)
      .range([0, chartWidth])
      .nice();

    const priceExtent = d3.extent(stockData.history, d => d.price);
    const padding = (priceExtent[1] - priceExtent[0]) * 0.1;
    this.scales.y = d3.scaleLinear()
      .domain([priceExtent[0] - padding, priceExtent[1] + padding])
      .range([chartHeight, 0])
      .nice();

    // Update axes
    const xAxis = d3.axisBottom(this.scales.x)
      .ticks(6)
      .tickFormat(d3.timeFormat('%b %d'));

    const yAxis = d3.axisLeft(this.scales.y)
      .ticks(5)
      .tickFormat(d => `$${d.toFixed(2)}`);

    this.chart.select('.axis-x')
      .attr('transform', `translate(0, ${chartHeight})`)
      .transition()
      .duration(750)
      .call(xAxis)
      .selectAll('text')
      .attr('fill', this.colors.textMuted)
      .style('font-size', '12px');

    this.chart.select('.axis-y')
      .transition()
      .duration(750)
      .call(yAxis)
      .selectAll('text')
      .attr('fill', this.colors.textMuted)
      .style('font-size', '12px');

    // Style axis lines
    this.chart.selectAll('.axis path, .axis line')
      .attr('stroke', this.colors.glassBorder)
      .attr('stroke-width', 1);

    // Grid lines
    this.chart.select('.grid-y')
      .transition()
      .duration(750)
      .call(d3.axisLeft(this.scales.y)
        .ticks(5)
        .tickSize(-chartWidth)
        .tickFormat('')
      )
      .selectAll('line')
      .attr('stroke', this.colors.glassBorder)
      .attr('stroke-opacity', 0.3)
      .attr('stroke-dasharray', '2,4');

    // Price area
    const area = d3.area()
      .x(d => this.scales.x(d.date))
      .y0(chartHeight)
      .y1(d => this.scales.y(d.price))
      .curve(d3.curveMonotoneX);

    const areaPath = this.chart.select('.price-area')
      .selectAll('path')
      .data([stockData.history]);

    areaPath.enter()
      .append('path')
      .attr('fill', `url(#price-gradient)`)
      .attr('opacity', 0.2)
      .merge(areaPath)
      .transition()
      .duration(750)
      .attr('d', area);

    // Gradient
    if (!this.svg.select('#price-gradient').size()) {
      const gradient = this.svg.select('defs')
        .append('linearGradient')
        .attr('id', 'price-gradient')
        .attr('x1', '0%')
        .attr('y1', '0%')
        .attr('x2', '0%')
        .attr('y2', '100%');

      gradient.append('stop')
        .attr('offset', '0%')
        .attr('stop-color', this.colors.up)
        .attr('stop-opacity', 0.4);

      gradient.append('stop')
        .attr('offset', '100%')
        .attr('stop-color', this.colors.up)
        .attr('stop-opacity', 0);
    }

    // Price line
    const line = d3.line()
      .x(d => this.scales.x(d.date))
      .y(d => this.scales.y(d.price))
      .curve(d3.curveMonotoneX);

    const linePath = this.chart.select('.price-line')
      .selectAll('path')
      .data([stockData.history]);

    linePath.enter()
      .append('path')
      .attr('fill', 'none')
      .attr('stroke', this.colors.up)
      .attr('stroke-width', 2)
      .merge(linePath)
      .transition()
      .duration(750)
      .attr('d', line);

    // Predictions
    if (stockData.predictions && stockData.predictions.length > 0) {
      this.drawPredictions(stockData.predictions, chartWidth, chartHeight);
    }

    // Interactive overlay
    this.addInteractivity(stockData.history, chartWidth, chartHeight);
  }

  drawPredictions(predictions, chartWidth, chartHeight) {
    // Confidence bands
    const bands = this.chart.select('.confidence-bands')
      .selectAll('.confidence-band')
      .data(predictions);

    const bandEnter = bands.enter()
      .append('g')
      .attr('class', 'confidence-band')
      .style('opacity', 0);

    // Background band
    bandEnter.append('rect')
      .attr('class', 'band-bg')
      .attr('fill', d => {
        if (d.prediction === 'up') return this.colors.up;
        if (d.prediction === 'down') return this.colors.down;
        return this.colors.flat;
      })
      .attr('opacity', d => this.getConfidenceOpacity(d.confidence));

    // Merge and update
    const bandMerge = bandEnter.merge(bands);

    bandMerge.select('.band-bg')
      .transition()
      .duration(750)
      .attr('x', d => this.scales.x(d.date) - 2)
      .attr('y', 0)
      .attr('width', 4)
      .attr('height', chartHeight);

    bandMerge
      .transition()
      .duration(750)
      .style('opacity', 1);

    bands.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();

    // Prediction markers
    const markers = this.chart.select('.predictions')
      .selectAll('.prediction-marker')
      .data(predictions);

    const markerEnter = markers.enter()
      .append('g')
      .attr('class', 'prediction-marker')
      .style('opacity', 0);

    // Marker circle
    markerEnter.append('circle')
      .attr('r', 6)
      .attr('fill', d => {
        if (d.prediction === 'up') return this.colors.up;
        if (d.prediction === 'down') return this.colors.down;
        return this.colors.flat;
      })
      .attr('stroke', '#0f172a')
      .attr('stroke-width', 2);

    // Prediction arrow
    markerEnter.append('path')
      .attr('fill', '#0f172a')
      .attr('d', d => {
        if (d.prediction === 'up') return 'M 0,-2.5 L -2,0.5 L 2,0.5 Z';
        if (d.prediction === 'down') return 'M 0,2.5 L -2,-0.5 L 2,-0.5 Z';
        return '';
      });

    // Merge and update
    const markerMerge = markerEnter.merge(markers);

    markerMerge
      .attr('transform', d => {
        const x = this.scales.x(d.date);
        const y = this.scales.y(d.price || 0);
        return `translate(${x}, ${y})`;
      })
      .style('cursor', 'pointer')
      .on('mouseenter', (event, d) => this.showPredictionTooltip(event, d))
      .on('mouseleave', () => this.hideTooltip());

    markerMerge
      .transition()
      .duration(750)
      .delay((d, i) => i * 50)
      .style('opacity', 1);

    markers.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();
  }

  addInteractivity(history, chartWidth, chartHeight) {
    // Remove old overlay
    this.chart.selectAll('.overlay').remove();

    // Invisible overlay for mouse tracking
    const overlay = this.chart.append('rect')
      .attr('class', 'overlay')
      .attr('width', chartWidth)
      .attr('height', chartHeight)
      .attr('fill', 'none')
      .attr('pointer-events', 'all')
      .on('mousemove', (event) => this.handleMouseMove(event, history))
      .on('mouseleave', () => this.hideTooltip());

    // Focus line
    this.chart.append('line')
      .attr('class', 'focus-line')
      .attr('stroke', this.colors.textMuted)
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '4,4')
      .attr('opacity', 0)
      .attr('y1', 0)
      .attr('y2', chartHeight);

    // Focus circle
    this.chart.append('circle')
      .attr('class', 'focus-circle')
      .attr('r', 4)
      .attr('fill', this.colors.up)
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .attr('opacity', 0);
  }

  handleMouseMove(event, history) {
    const [mouseX] = d3.pointer(event);
    const x0 = this.scales.x.invert(mouseX);
    const bisect = d3.bisector(d => d.date).left;
    const i = bisect(history, x0, 1);
    const d0 = history[i - 1];
    const d1 = history[i];
    if (!d0 || !d1) return;

    const d = x0 - d0.date > d1.date - x0 ? d1 : d0;

    // Update focus elements
    const x = this.scales.x(d.date);
    const y = this.scales.y(d.price);

    this.chart.select('.focus-line')
      .attr('x1', x)
      .attr('x2', x)
      .attr('opacity', 0.5);

    this.chart.select('.focus-circle')
      .attr('cx', x)
      .attr('cy', y)
      .attr('opacity', 1);

    // Show tooltip
    this.showPriceTooltip(event, d);
  }

  showPriceTooltip(event, d) {
    const formatDate = d3.timeFormat('%B %d, %Y');
    const html = `
      <div style="font-weight: 600; margin-bottom: 4px;">${this.currentStock.symbol}</div>
      <div style="color: ${this.colors.textMuted}; font-size: 11px; margin-bottom: 8px;">${formatDate(d.date)}</div>
      <div style="font-size: 16px; color: ${this.colors.up};">$${d.price.toFixed(2)}</div>
    `;

    this.tooltip
      .html(html)
      .style('opacity', 1)
      .style('left', `${event.pageX + 10}px`)
      .style('top', `${event.pageY - 10}px`);
  }

  showPredictionTooltip(event, d) {
    const formatDate = d3.timeFormat('%B %d, %Y');
    const predictionColor = d.prediction === 'up' ? this.colors.up :
                           d.prediction === 'down' ? this.colors.down :
                           this.colors.flat;

    const html = `
      <div style="font-weight: 600; margin-bottom: 4px;">Prediction</div>
      <div style="color: ${this.colors.textMuted}; font-size: 11px; margin-bottom: 8px;">${formatDate(d.date)}</div>
      <div style="color: ${predictionColor}; text-transform: uppercase; font-weight: 600;">${d.prediction}</div>
      <div style="margin-top: 6px; font-size: 11px;">
        Confidence: <span style="color: ${this.colors.text};">${(d.confidence * 100).toFixed(0)}%</span>
      </div>
      ${d.provider ? `<div style="font-size: 11px; color: ${this.colors.textMuted}; margin-top: 4px;">${d.provider}</div>` : ''}
    `;

    this.tooltip
      .html(html)
      .style('opacity', 1)
      .style('left', `${event.pageX + 10}px`)
      .style('top', `${event.pageY - 10}px`);
  }

  hideTooltip() {
    this.tooltip.style('opacity', 0);
    this.chart.select('.focus-line').attr('opacity', 0);
    this.chart.select('.focus-circle').attr('opacity', 0);
  }

  getConfidenceOpacity(confidence) {
    if (confidence >= 0.9) return 1.0;    // 90-100% - fully opaque
    if (confidence >= 0.7) return 0.75;   // 70-89% - strong
    if (confidence >= 0.5) return 0.6;    // 50-69% - moderate (improved visibility)
    return 0.4;                           // <50% - uncertain (improved visibility)
  }

  showEmpty() {
    this.chart.selectAll('*').remove();
    this.chart.append('text')
      .attr('x', this.options.width / 2 - this.options.margin.left)
      .attr('y', this.options.height / 2 - this.options.margin.top)
      .attr('text-anchor', 'middle')
      .attr('fill', this.colors.textMuted)
      .attr('font-size', 14)
      .text('Select a stock to view details');
  }

  destroy() {
    if (this.svg) {
      this.svg.remove();
    }
    if (this.tooltip) {
      this.tooltip.remove();
    }
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = StockDetail;
}
