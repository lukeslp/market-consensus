/**
 * Sidebar Visualization
 * D3.js v7 - Provider statistics and leaderboard
 */

class Sidebar {
  constructor(container, options = {}) {
    this.container = d3.select(container);
    this.options = {
      width: options.width || 300,
      ...options
    };

    this.colors = {
      up: getComputedStyle(document.documentElement).getPropertyValue('--stock-up').trim(),
      down: getComputedStyle(document.documentElement).getPropertyValue('--stock-down').trim(),
      flat: getComputedStyle(document.documentElement).getPropertyValue('--stock-flat').trim(),
      background: getComputedStyle(document.documentElement).getPropertyValue('--bg-secondary').trim(),
      text: getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim(),
      textMuted: getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim(),
      accentPrimary: getComputedStyle(document.documentElement).getPropertyValue('--accent-primary').trim(),
      glassBg: 'rgba(255, 255, 255, 0.05)',
      glassBorder: 'rgba(255, 255, 255, 0.1)'
    };

    this.svg = null;
    this.init();
  }

  init() {
    // Container for stats cards
    this.statsContainer = this.container
      .append('div')
      .attr('class', 'sidebar-stats');

    // Leaderboard SVG
    this.svg = this.container
      .append('svg')
      .attr('width', this.options.width)
      .attr('role', 'img')
      .attr('aria-label', 'Provider accuracy leaderboard')
      .classed('sidebar-leaderboard', true);
  }

  update(stats) {
    // API returns {by_provider: [], overall_accuracy, total_predictions, completed_cycles, total_cycles}
    // Transform to expected format {summary: {...}, providers: [...]}
    if (!stats) {
      this.showEmpty();
      return;
    }

    const summary = {
      total_predictions: stats.total_predictions || 0,
      accuracy_rate: stats.overall_accuracy,
      active_stocks: 0, // Not provided by current API
      avg_confidence: null, // Not provided by current API
      completed_cycles: stats.completed_cycles || 0
    };

    const providers = stats.by_provider || [];

    if (providers.length === 0) {
      this.showEmpty();
      return;
    }

    this.updateStats(summary);
    this.updateLeaderboard(providers);
  }

  updateStats(summary) {
    if (!summary) return;

    const statsData = [
      {
        label: 'Total Predictions',
        value: summary.total_predictions || 0,
        icon: '📊'
      },
      {
        label: 'Accuracy Rate',
        value: summary.accuracy_rate ? `${(summary.accuracy_rate * 100).toFixed(1)}%` : 'N/A',
        icon: '🎯',
        color: summary.accuracy_rate >= 0.7 ? this.colors.up :
               summary.accuracy_rate >= 0.5 ? '#fbbf24' :
               this.colors.down
      },
      {
        label: 'Active Stocks',
        value: summary.active_stocks || 0,
        icon: '📈'
      },
      {
        label: 'Avg Confidence',
        value: summary.avg_confidence ? `${(summary.avg_confidence * 100).toFixed(0)}%` : 'N/A',
        icon: '💪'
      }
    ];

    // Bind data
    const cards = this.statsContainer
      .selectAll('.stat-card')
      .data(statsData, d => d.label);

    // Enter
    const cardEnter = cards.enter()
      .append('div')
      .attr('class', 'stat-card')
      .style('background', this.colors.glassBg)
      .style('border', `1px solid ${this.colors.glassBorder}`)
      .style('border-radius', '4px')
      .style('padding', '16px')
      .style('margin-bottom', '12px')
      .style('opacity', 0);

    cardEnter.append('div')
      .attr('class', 'stat-icon')
      .attr('aria-hidden', 'true')
      .style('font-size', '24px')
      .style('margin-bottom', '8px')
      .text(d => d.icon);

    cardEnter.append('div')
      .attr('class', 'stat-value')
      .style('font-size', '28px')
      .style('font-weight', '700')
      .style('margin-bottom', '4px');

    cardEnter.append('div')
      .attr('class', 'stat-label')
      .style('font-size', '12px')
      .style('color', this.colors.textMuted)
      .style('text-transform', 'uppercase')
      .style('letter-spacing', '0.05em')
      .text(d => d.label);

    // Update
    const cardMerge = cardEnter.merge(cards);

    cardMerge.select('.stat-value')
      .style('color', d => d.color || this.colors.text)
      .text(d => d.value);

    cardMerge
      .transition()
      .duration(750)
      .style('opacity', 1);

    // Exit
    cards.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();
  }

  updateLeaderboard(providers) {
    // Sort by accuracy descending
    providers.sort((a, b) => (b.accuracy || 0) - (a.accuracy || 0));

    const rowHeight = 80;
    const headerHeight = 60;
    const height = headerHeight + providers.length * rowHeight + 20;

    this.svg
      .transition()
      .duration(750)
      .attr('height', height);

    // Header
    let header = this.svg.selectAll('.leaderboard-header').data([null]);
    const headerEnter = header.enter()
      .append('g')
      .attr('class', 'leaderboard-header');

    headerEnter.append('text')
      .attr('x', 16)
      .attr('y', 30)
      .attr('font-size', 18)
      .attr('font-weight', 600)
      .attr('fill', this.colors.text)
      .text('🏆 Provider Leaderboard');

    headerEnter.append('line')
      .attr('x1', 16)
      .attr('x2', this.options.width - 16)
      .attr('y1', headerHeight - 10)
      .attr('y2', headerHeight - 10)
      .attr('stroke', this.colors.glassBorder)
      .attr('stroke-width', 1);

    // Provider rows
    const rows = this.svg.selectAll('.provider-row')
      .data(providers, d => d.provider);

    // Enter
    const rowEnter = rows.enter()
      .append('g')
      .attr('class', 'provider-row')
      .attr('transform', (d, i) => `translate(0, ${headerHeight + i * rowHeight})`)
      .style('opacity', 0);

    // Background
    rowEnter.append('rect')
      .attr('class', 'row-bg')
      .attr('x', 8)
      .attr('y', 5)
      .attr('width', this.options.width - 16)
      .attr('height', rowHeight - 10)
      .attr('rx', 8)
      .attr('fill', this.colors.glassBg)
      .attr('stroke', this.colors.glassBorder)
      .attr('stroke-width', 1);

    // Rank badge
    rowEnter.append('circle')
      .attr('class', 'rank-badge')
      .attr('cx', 30)
      .attr('cy', rowHeight / 2)
      .attr('r', 14)
      .attr('fill', (d, i) => {
        if (i === 0) return '#fbbf24'; // Gold
        if (i === 1) return '#94a3b8'; // Silver
        if (i === 2) return '#d97706'; // Bronze
        return this.colors.background;
      });

    rowEnter.append('text')
      .attr('class', 'rank-text')
      .attr('x', 30)
      .attr('y', rowHeight / 2)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', 12)
      .attr('font-weight', 600)
      .attr('fill', this.colors.text)
      .text((d, i) => i + 1);

    // Provider name
    rowEnter.append('text')
      .attr('class', 'provider-name')
      .attr('x', 55)
      .attr('y', rowHeight / 2 - 8)
      .attr('font-size', 14)
      .attr('font-weight', 600)
      .attr('fill', this.colors.text)
      .text(d => this.formatProviderName(d.provider));

    // Prediction count
    rowEnter.append('text')
      .attr('class', 'prediction-count')
      .attr('x', 55)
      .attr('y', rowHeight / 2 + 12)
      .attr('font-size', 11)
      .attr('fill', this.colors.textMuted)
      .text(d => `${d.total_predictions || 0} predictions`);

    // Accuracy bar background
    rowEnter.append('rect')
      .attr('class', 'accuracy-bg')
      .attr('x', this.options.width - 140)
      .attr('y', rowHeight / 2 - 8)
      .attr('width', 80)
      .attr('height', 16)
      .attr('rx', 8)
      .attr('fill', this.colors.background)
      .attr('stroke', this.colors.glassBorder)
      .attr('stroke-width', 1);

    // Accuracy bar fill
    rowEnter.append('rect')
      .attr('class', 'accuracy-fill')
      .attr('x', this.options.width - 140)
      .attr('y', rowHeight / 2 - 8)
      .attr('width', 0)
      .attr('height', 16)
      .attr('rx', 8);

    // Accuracy percentage text
    rowEnter.append('text')
      .attr('class', 'accuracy-text')
      .attr('x', this.options.width - 30)
      .attr('y', rowHeight / 2)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', 12)
      .attr('font-weight', 600);

    // Update
    const rowMerge = rowEnter.merge(rows);

    // Animate positions
    rowMerge
      .transition()
      .duration(750)
      .attr('transform', (d, i) => `translate(0, ${headerHeight + i * rowHeight})`)
      .style('opacity', 1);

    // Update rank badges
    rowMerge.select('.rank-badge')
      .transition()
      .duration(750)
      .attr('fill', (d, i) => {
        if (i === 0) return '#fbbf24';
        if (i === 1) return '#94a3b8';
        if (i === 2) return '#d97706';
        return this.colors.background;
      });

    rowMerge.select('.rank-text')
      .transition()
      .duration(750)
      .text((d, i) => i + 1);

    // Update accuracy bars
    rowMerge.select('.accuracy-fill')
      .transition()
      .duration(1000)
      .ease(d3.easeCubicOut)
      .attr('width', d => {
        const accuracy = d.accuracy || 0;
        return 80 * accuracy;
      })
      .attr('fill', d => {
        const accuracy = d.accuracy || 0;
        if (accuracy >= 0.7) return this.colors.up;
        if (accuracy >= 0.5) return '#fbbf24';
        return this.colors.down;
      });

    // Update accuracy text
    rowMerge.select('.accuracy-text')
      .transition()
      .duration(1000)
      .tween('text', function(d) {
        const i = d3.interpolateNumber(0, (d.accuracy || 0) * 100);
        return function(t) {
          d3.select(this).text(`${i(t).toFixed(0)}%`);
        };
      })
      .attr('fill', d => {
        const accuracy = d.accuracy || 0;
        if (accuracy >= 0.7) return this.colors.up;
        if (accuracy >= 0.5) return '#fbbf24';
        return this.colors.down;
      });

    // Update prediction count
    rowMerge.select('.prediction-count')
      .text(d => `${d.total_predictions || 0} predictions`);

    // Hover effects (arrow functions so `this` stays the Sidebar instance)
    rowMerge
      .on('mouseenter', (event) => {
        d3.select(event.currentTarget).select('.row-bg')
          .transition()
          .duration(200)
          .attr('stroke', this.colors.accentPrimary)
          .attr('stroke-width', 2);
      })
      .on('mouseleave', (event) => {
        d3.select(event.currentTarget).select('.row-bg')
          .transition()
          .duration(200)
          .attr('stroke', this.colors.glassBorder)
          .attr('stroke-width', 1);
      })
      .style('cursor', 'pointer');

    // Exit
    rows.exit()
      .transition()
      .duration(500)
      .style('opacity', 0)
      .remove();
  }

  formatProviderName(provider) {
    const names = {
      'anthropic': 'Anthropic',
      'xai': 'xAI',
      'gemini': 'Gemini',
      'openai': 'OpenAI',
      'mistral': 'Mistral',
      'cohere': 'Cohere',
      'perplexity': 'Perplexity'
    };
    return names[provider] || provider.charAt(0).toUpperCase() + provider.slice(1);
  }

  showEmpty() {
    this.statsContainer.selectAll('*').remove();
    this.svg.selectAll('*').remove();

    this.svg.attr('height', 200);
    this.svg.append('text')
      .attr('x', this.options.width / 2)
      .attr('y', 100)
      .attr('text-anchor', 'middle')
      .attr('fill', this.colors.textMuted)
      .attr('font-size', 14)
      .text('No provider statistics available');
  }

  destroy() {
    this.statsContainer.remove();
    if (this.svg) {
      this.svg.remove();
    }
  }
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Sidebar;
}
