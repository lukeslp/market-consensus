/**
 * Prediction Accuracy Timeline
 * Multi-provider line chart with confidence bands
 * D3.js v7 - "Life is Beautiful" aesthetic
 */

class PredictionTimeline {
  constructor(container, options = {}) {
    this.container = d3.select(container);
    this.options = {
      width: options.width || 800,
      height: options.height || 300,
      margin: options.margin || { top: 20, right: 100, bottom: 40, left: 60 },
      providers: options.providers || ['xai', 'anthropic', 'gemini'],
      ...options
    };

    // Provider colors (colorblind-safe palette)
    this.providerColors = {
      xai: '#117733',      // Green
      anthropic: '#332288', // Blue
      gemini: '#882255'    // Wine
    };

    this.svg = null;
    this.xScale = null;
    this.yScale = null;
    this.line = null;
    this.data = [];

    this.init();
  }

  init() {
    const { width, height, margin } = this.options;
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    // Create SVG
    this.svg = this.container
      .append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .classed('prediction-timeline', true);

    // Main group
    this.g = this.svg
      .append('g')
      .attr('transform', `translate(${margin.left}, ${margin.top})`);

    // Scales
    this.xScale = d3.scaleTime()
      .range([0, innerWidth]);

    this.yScale = d3.scaleLinear()
      .domain([0, 1])
      .range([innerHeight, 0]);

    // Line generator
    this.line = d3.line()
      .x(d => this.xScale(new Date(d.timestamp)))
      .y(d => this.yScale(d.accuracy))
      .curve(d3.curveCatmullRom.alpha(0.5)); // Smooth curve

    // Axes
    this.xAxis = this.g.append('g')
      .attr('class', 'x-axis')
      .attr('transform', `translate(0, ${innerHeight})`);

    this.yAxis = this.g.append('g')
      .attr('class', 'y-axis');

    // Grid lines
    this.yGrid = this.g.append('g')
      .attr('class', 'grid');

    // Clip path for smooth updates
    this.svg.append('defs')
      .append('clipPath')
      .attr('id', 'timeline-clip')
      .append('rect')
      .attr('width', innerWidth)
      .attr('height', innerHeight);

    // Lines container
    this.linesGroup = this.g.append('g')
      .attr('clip-path', 'url(#timeline-clip)')
      .attr('class', 'lines');

    // Confidence bands container
    this.bandsGroup = this.g.append('g')
      .attr('clip-path', 'url(#timeline-clip)')
      .attr('class', 'confidence-bands');

    // Points container
    this.pointsGroup = this.g.append('g')
      .attr('clip-path', 'url(#timeline-clip)')
      .attr('class', 'points');

    // Legend
    this.legend = this.g.append('g')
      .attr('class', 'legend')
      .attr('transform', `translate(${innerWidth + 10}, 0)`);

    this.updateAxes();
  }

  updateAxes() {
    const { height, margin } = this.options;
    const innerHeight = height - margin.top - margin.bottom;

    // X axis
    const xAxisGenerator = d3.axisBottom(this.xScale)
      .ticks(6)
      .tickFormat(d3.timeFormat('%H:%M'));

    this.xAxis.call(xAxisGenerator)
      .selectAll('text')
      .style('fill', '#94a3b8')
      .style('font-size', '12px');

    this.xAxis.selectAll('line, path')
      .style('stroke', '#334155');

    // Y axis
    const yAxisGenerator = d3.axisLeft(this.yScale)
      .ticks(5)
      .tickFormat(d => `${(d * 100).toFixed(0)}%`);

    this.yAxis.call(yAxisGenerator)
      .selectAll('text')
      .style('fill', '#94a3b8')
      .style('font-size', '12px');

    this.yAxis.selectAll('line, path')
      .style('stroke', '#334155');

    // Grid
    this.yGrid.call(
      d3.axisLeft(this.yScale)
        .ticks(5)
        .tickSize(-this.options.width + this.options.margin.left + this.options.margin.right)
        .tickFormat('')
    )
      .selectAll('line')
      .style('stroke', '#334155')
      .style('stroke-opacity', 0.3)
      .style('stroke-dasharray', '2,2');

    this.yGrid.select('.domain').remove();
  }

  update(data) {
    this.data = data;

    // Group by provider
    const byProvider = d3.group(data, d => d.provider);

    // Update time scale domain
    const timeExtent = d3.extent(data, d => new Date(d.timestamp));
    this.xScale.domain(timeExtent).nice();
    this.updateAxes();

    // Update confidence bands
    const bandData = Array.from(byProvider, ([provider, values]) => ({
      provider,
      values: values.map(d => ({
        timestamp: new Date(d.timestamp),
        accuracy: d.accuracy,
        confidence: d.avg_confidence || 0.8
      }))
    }));

    const bands = this.bandsGroup
      .selectAll('.confidence-band')
      .data(bandData, d => d.provider);

    // Enter
    const bandsEnter = bands.enter()
      .append('path')
      .attr('class', 'confidence-band')
      .style('fill', d => this.providerColors[d.provider])
      .style('opacity', 0);

    // Update
    bands.merge(bandsEnter)
      .transition()
      .duration(750)
      .style('opacity', 0.15)
      .attr('d', d => this.confidenceBand(d.values));

    // Exit
    bands.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();

    // Update lines
    const lines = this.linesGroup
      .selectAll('.accuracy-line')
      .data(Array.from(byProvider, ([provider, values]) => ({ provider, values })), d => d.provider);

    // Enter
    const linesEnter = lines.enter()
      .append('path')
      .attr('class', 'accuracy-line')
      .style('fill', 'none')
      .style('stroke', d => this.providerColors[d.provider])
      .style('stroke-width', 2.5)
      .style('opacity', 0);

    // Update
    lines.merge(linesEnter)
      .transition()
      .duration(750)
      .ease(d3.easeCubicInOut)
      .style('opacity', 1)
      .attr('d', d => this.line(d.values));

    // Exit
    lines.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();

    // Update points
    const points = this.pointsGroup
      .selectAll('.data-point')
      .data(data, d => `${d.provider}-${d.timestamp}`);

    // Enter
    const pointsEnter = points.enter()
      .append('circle')
      .attr('class', 'data-point')
      .attr('r', 0)
      .attr('cx', d => this.xScale(new Date(d.timestamp)))
      .attr('cy', d => this.yScale(d.accuracy))
      .style('fill', d => this.providerColors[d.provider])
      .style('stroke', '#1e293b')
      .style('stroke-width', 2);

    // Update
    points.merge(pointsEnter)
      .on('mouseenter', (event, d) => this.showTooltip(event, d))
      .on('mouseleave', () => this.hideTooltip())
      .transition()
      .duration(750)
      .attr('cx', d => this.xScale(new Date(d.timestamp)))
      .attr('cy', d => this.yScale(d.accuracy))
      .attr('r', 4);

    // Exit
    points.exit()
      .transition()
      .duration(500)
      .attr('r', 0)
      .remove();

    // Update legend
    this.updateLegend(Array.from(byProvider.keys()));
  }

  confidenceBand(values) {
    const bandwidth = 0.1; // ±10% confidence band
    const area = d3.area()
      .x(d => this.xScale(d.timestamp))
      .y0(d => this.yScale(Math.max(0, d.accuracy - bandwidth)))
      .y1(d => this.yScale(Math.min(1, d.accuracy + bandwidth)))
      .curve(d3.curveCatmullRom.alpha(0.5));

    return area(values);
  }

  updateLegend(providers) {
    const legendItems = this.legend
      .selectAll('.legend-item')
      .data(providers);

    const itemsEnter = legendItems.enter()
      .append('g')
      .attr('class', 'legend-item')
      .attr('transform', (d, i) => `translate(0, ${i * 25})`)
      .style('cursor', 'pointer')
      .on('click', (event, provider) => this.toggleProvider(provider));

    itemsEnter.append('line')
      .attr('x1', 0)
      .attr('x2', 20)
      .attr('y1', 0)
      .attr('y2', 0)
      .style('stroke', d => this.providerColors[d])
      .style('stroke-width', 2.5);

    itemsEnter.append('text')
      .attr('x', 30)
      .attr('y', 5)
      .style('fill', '#cbd5e1')
      .style('font-size', '14px')
      .text(d => d.charAt(0).toUpperCase() + d.slice(1));

    legendItems.exit().remove();
  }

  toggleProvider(provider) {
    // Toggle visibility (TODO: implement filtering)
    console.log('Toggle provider:', provider);
  }

  showTooltip(event, d) {
    // TODO: Implement tooltip
    console.log('Show tooltip:', d);
  }

  hideTooltip() {
    // TODO: Implement tooltip hide
  }

  destroy() {
    if (this.svg) {
      this.svg.remove();
    }
  }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PredictionTimeline;
}
