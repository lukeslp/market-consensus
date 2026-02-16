/**
 * Provider Leaderboard
 * Horizontal bar chart with accuracy comparison
 * D3.js v7 - Mathematical elegance meets emotional storytelling
 */

class ProviderLeaderboard {
  constructor(container, options = {}) {
    this.container = d3.select(container);
    this.options = {
      width: options.width || 400,
      height: options.height || 250,
      margin: options.margin || { top: 20, right: 60, bottom: 30, left: 100 },
      ...options
    };

    // Provider colors (colorblind-safe)
    this.providerColors = {
      xai: '#117733',
      anthropic: '#332288',
      gemini: '#882255'
    };

    this.providerNames = {
      xai: 'Grok (xAI)',
      anthropic: 'Claude',
      gemini: 'Gemini'
    };

    this.svg = null;
    this.xScale = null;
    this.yScale = null;
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
      .classed('provider-leaderboard', true);

    // Main group
    this.g = this.svg
      .append('g')
      .attr('transform', `translate(${margin.left}, ${margin.top})`);

    // Scales
    this.xScale = d3.scaleLinear()
      .domain([0, 1])
      .range([0, innerWidth]);

    this.yScale = d3.scaleBand()
      .range([0, innerHeight])
      .padding(0.3);

    // Axes
    this.xAxis = this.g.append('g')
      .attr('class', 'x-axis')
      .attr('transform', `translate(0, ${innerHeight})`);

    this.yAxis = this.g.append('g')
      .attr('class', 'y-axis');

    // Bars container
    this.barsGroup = this.g.append('g')
      .attr('class', 'bars');

    // Labels container
    this.labelsGroup = this.g.append('g')
      .attr('class', 'labels');

    this.updateAxes();
  }

  updateAxes() {
    // X axis
    const xAxisGenerator = d3.axisBottom(this.xScale)
      .ticks(5)
      .tickFormat(d => `${(d * 100).toFixed(0)}%`);

    this.xAxis.call(xAxisGenerator)
      .selectAll('text')
      .style('fill', '#94a3b8')
      .style('font-size', '12px');

    this.xAxis.selectAll('line, path')
      .style('stroke', '#334155');

    // Y axis
    this.yAxis.call(d3.axisLeft(this.yScale))
      .selectAll('text')
      .style('fill', '#cbd5e1')
      .style('font-size', '14px')
      .style('font-weight', '500');

    this.yAxis.selectAll('line, path')
      .style('stroke', '#334155');
  }

  update(data) {
    // Sort by accuracy (descending)
    this.data = [...data].sort((a, b) => b.accuracy - a.accuracy);

    // Update Y scale domain
    this.yScale.domain(this.data.map(d => this.providerNames[d.provider] || d.provider));
    this.updateAxes();

    // Update bars
    const bars = this.barsGroup
      .selectAll('.provider-bar')
      .data(this.data, d => d.provider);

    // Enter
    const barsEnter = bars.enter()
      .append('rect')
      .attr('class', 'provider-bar')
      .attr('x', 0)
      .attr('y', d => this.yScale(this.providerNames[d.provider] || d.provider))
      .attr('width', 0)
      .attr('height', this.yScale.bandwidth())
      .attr('rx', 6)
      .style('fill', d => this.providerColors[d.provider] || '#64748b')
      .style('cursor', 'pointer')
      .on('mouseenter', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .style('filter', 'brightness(1.2)');
      })
      .on('mouseleave', function() {
        d3.select(this)
          .transition()
          .duration(200)
          .style('filter', 'brightness(1)');
      });

    // Update
    bars.merge(barsEnter)
      .transition()
      .duration(1000)
      .ease(d3.easeBackOut.overshoot(1.2))
      .attr('y', d => this.yScale(this.providerNames[d.provider] || d.provider))
      .attr('width', d => this.xScale(d.accuracy))
      .attr('height', this.yScale.bandwidth());

    // Exit
    bars.exit()
      .transition()
      .duration(500)
      .attr('width', 0)
      .remove();

    // Update accuracy labels
    const labels = this.labelsGroup
      .selectAll('.accuracy-label')
      .data(this.data, d => d.provider);

    // Enter
    const labelsEnter = labels.enter()
      .append('text')
      .attr('class', 'accuracy-label')
      .attr('x', 0)
      .attr('y', d => this.yScale(this.providerNames[d.provider] || d.provider) + this.yScale.bandwidth() / 2)
      .attr('dy', '0.35em')
      .style('fill', '#f1f5f9')
      .style('font-size', '14px')
      .style('font-weight', '600')
      .style('opacity', 0);

    // Update
    labels.merge(labelsEnter)
      .transition()
      .duration(1000)
      .attr('y', d => this.yScale(this.providerNames[d.provider] || d.provider) + this.yScale.bandwidth() / 2)
      .attr('x', d => this.xScale(d.accuracy) + 10)
      .style('opacity', 1)
      .textTween(function(d) {
        const i = d3.interpolate(0, d.accuracy);
        return function(t) {
          return `${(i(t) * 100).toFixed(1)}%`;
        };
      });

    // Exit
    labels.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();

    // Update prediction count badges
    const badges = this.labelsGroup
      .selectAll('.prediction-count')
      .data(this.data, d => d.provider);

    // Enter
    const badgesEnter = badges.enter()
      .append('g')
      .attr('class', 'prediction-count')
      .attr('transform', d => {
        const y = this.yScale(this.providerNames[d.provider] || d.provider) + this.yScale.bandwidth() / 2;
        return `translate(${this.xScale(1) + 10}, ${y})`;
      })
      .style('opacity', 0);

    badgesEnter.append('circle')
      .attr('r', 12)
      .style('fill', 'rgba(255, 255, 255, 0.1)')
      .style('stroke', 'rgba(255, 255, 255, 0.3)')
      .style('stroke-width', 1);

    badgesEnter.append('text')
      .attr('dy', '0.35em')
      .attr('text-anchor', 'middle')
      .style('fill', '#cbd5e1')
      .style('font-size', '11px')
      .style('font-weight', '500');

    // Update
    badges.merge(badgesEnter)
      .transition()
      .duration(1000)
      .attr('transform', d => {
        const y = this.yScale(this.providerNames[d.provider] || d.provider) + this.yScale.bandwidth() / 2;
        return `translate(${this.xScale(1) + 10}, ${y})`;
      })
      .style('opacity', 1);

    badges.merge(badgesEnter)
      .select('text')
      .transition()
      .duration(1000)
      .textTween(function(d) {
        const i = d3.interpolate(0, d.total || 0);
        return function(t) {
          return Math.round(i(t));
        };
      });

    // Exit
    badges.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();

    // Add rank medals for top 3
    this.addRankMedals();
  }

  addRankMedals() {
    const medals = ['🥇', '🥈', '🥉'];

    const medalElements = this.g
      .selectAll('.rank-medal')
      .data(this.data.slice(0, 3), d => d.provider);

    const medalsEnter = medalElements.enter()
      .append('text')
      .attr('class', 'rank-medal')
      .attr('x', -20)
      .attr('y', d => this.yScale(this.providerNames[d.provider] || d.provider) + this.yScale.bandwidth() / 2)
      .attr('dy', '0.35em')
      .attr('text-anchor', 'middle')
      .style('font-size', '18px')
      .style('opacity', 0)
      .text((d, i) => medals[i]);

    medalElements.merge(medalsEnter)
      .transition()
      .duration(1000)
      .delay((d, i) => i * 100)
      .style('opacity', 1)
      .attr('y', d => this.yScale(this.providerNames[d.provider] || d.provider) + this.yScale.bandwidth() / 2);

    medalElements.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();
  }

  destroy() {
    if (this.svg) {
      this.svg.remove();
    }
  }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ProviderLeaderboard;
}
