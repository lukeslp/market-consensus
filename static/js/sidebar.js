class Sidebar {
  constructor(containerSelector, options = {}) {
    this.container = d3.select(containerSelector);
    this.options = { width: options.width || 280, ...options };
    this.colors = this.readColors();

    this.statsWrap = null;
    this.svg = null;
    this.init();
  }

  readColors() {
    const css = getComputedStyle(document.documentElement);
    return {
      ink: css.getPropertyValue('--ink').trim(),
      muted: css.getPropertyValue('--muted').trim(),
      line: css.getPropertyValue('--line').trim(),
      up: css.getPropertyValue('--up').trim(),
      down: css.getPropertyValue('--down').trim(),
      accent: css.getPropertyValue('--accent').trim()
    };
  }

  init() {
    this.container.html('');
    this.statsWrap = this.container.append('div').attr('class', 'sidebar-stats');
    this.svg = this.container.append('svg').attr('class', 'sidebar-leaderboard').attr('role', 'list');
  }

  update(payload) {
    if (!payload || !Array.isArray(payload.by_provider) || payload.by_provider.length === 0) {
      this.showEmpty();
      return;
    }

    this.renderStats(payload);
    this.renderLeaderboard(payload.by_provider.slice());
  }

  renderStats(payload) {
    const rows = [
      { label: 'Completed Cycles', value: payload.completed_cycles ?? 0 },
      { label: 'Total Cycles', value: payload.total_cycles ?? 0 },
      { label: 'Predictions', value: payload.total_predictions ?? 0 },
      { label: 'Overall Accuracy', value: Number.isFinite(+payload.overall_accuracy) ? `${(+payload.overall_accuracy * 100).toFixed(1)}%` : 'N/A' }
    ];

    const cards = this.statsWrap.selectAll('article.stat').data(rows, (d) => d.label);
    const enter = cards.enter().append('article').attr('class', 'stat')
      .style('padding', '0.55rem 0.65rem')
      .style('border', `1px solid ${this.colors.line}`)
      .style('border-radius', '8px')
      .style('margin-bottom', '0.45rem')
      .style('background', 'rgba(255,255,255,0.02)');

    enter.append('p').attr('class', 'stat-label').style('margin', '0').style('color', this.colors.muted).style('font-size', '0.68rem');
    enter.append('p').attr('class', 'stat-value').style('margin', '0.2rem 0 0').style('font-size', '1rem').style('font-weight', '600');

    const merged = enter.merge(cards);
    merged.select('.stat-label').text((d) => d.label);
    merged.select('.stat-value').text((d) => d.value).style('color', this.colors.ink);

    cards.exit().remove();
  }

  renderLeaderboard(providers) {
    providers.sort((a, b) => (+b.accuracy_rate || 0) - (+a.accuracy_rate || 0));

    const rowH = 46;
    const width = this.options.width;
    const height = providers.length * rowH + 10;
    this.svg.attr('viewBox', `0 0 ${width} ${height}`).attr('height', height);

    const rows = this.svg.selectAll('g.row').data(providers, (d) => d.provider);
    const enter = rows.enter().append('g').attr('class', 'row').attr('role', 'listitem').attr('tabindex', 0);

    enter.append('rect').attr('class', 'row-bg').attr('x', 2).attr('rx', 8).attr('ry', 8).attr('width', width - 4).attr('height', rowH - 6);
    enter.append('text').attr('class', 'provider-name').attr('x', 10).attr('y', 19);
    enter.append('text').attr('class', 'provider-meta').attr('x', 10).attr('y', 34);
    enter.append('rect').attr('class', 'accuracy-track').attr('x', width - 118).attr('y', 16).attr('width', 78).attr('height', 10).attr('rx', 999);
    enter.append('rect').attr('class', 'accuracy-fill').attr('x', width - 118).attr('y', 16).attr('height', 10).attr('rx', 999);
    enter.append('text').attr('class', 'accuracy-text').attr('x', width - 20).attr('y', 24).attr('text-anchor', 'middle');

    const merged = enter.merge(rows).attr('transform', (d, i) => `translate(0,${i * rowH})`);

    merged.select('.row-bg').attr('fill', 'rgba(255,255,255,0.02)').attr('stroke', this.colors.line);
    merged.select('.provider-name').attr('fill', this.colors.ink).attr('font-size', 12).attr('font-family', 'var(--font-display)').text((d, i) => `#${i + 1} ${this.prettyProvider(d.provider)}`);
    merged.select('.provider-meta').attr('fill', this.colors.muted).attr('font-size', 10).attr('font-family', 'var(--font-data)').text((d) => this.getProviderModel(d.provider) || `${d.total_predictions || 0} predictions`);
    merged.select('.accuracy-track').attr('fill', 'rgba(255,255,255,0.08)');
    merged.select('.accuracy-fill')
      .attr('fill', (d) => this.accuracyColor(+d.accuracy_rate || 0))
      .transition().duration(420)
      .attr('width', (d) => 78 * Math.max(0, Math.min(1, +d.accuracy_rate || 0)));
    merged.select('.accuracy-text').attr('fill', this.colors.ink).attr('font-size', 10).attr('font-family', 'var(--font-data)').text((d) => `${Math.round((+d.accuracy_rate || 0) * 100)}%`);

    merged
      .attr('aria-label', (d, i) => `Rank ${i + 1}, ${this.prettyProvider(d.provider)}, ${d.total_predictions || 0} predictions, ${Math.round((+d.accuracy_rate || 0) * 100)} percent accuracy`)
      .on('focusin', (event) => d3.select(event.currentTarget).select('.row-bg').attr('stroke', this.colors.accent))
      .on('focusout', (event) => d3.select(event.currentTarget).select('.row-bg').attr('stroke', this.colors.line))
      .on('mouseenter', (event) => d3.select(event.currentTarget).select('.row-bg').attr('stroke', this.colors.accent))
      .on('mouseleave', (event) => d3.select(event.currentTarget).select('.row-bg').attr('stroke', this.colors.line));

    rows.exit().remove();
  }

  accuracyColor(value) {
    if (value >= 0.7) return this.colors.up;
    if (value >= 0.5) return this.colors.accent;
    return this.colors.down;
  }

  prettyProvider(raw = '') {
    const map = { 
      xai: 'xAI', 
      anthropic: 'Anthropic', 
      gemini: 'Gemini', 
      mistral: 'Mistral', 
      perplexity: 'Perplexity', 
      openai: 'OpenAI',
      cohere: 'Cohere',
      huggingface: 'HuggingFace'
    };
    return map[raw] || `${raw}`;
  }

  getProviderModel(provider) {
    const models = {
      anthropic: 'claude-sonnet-4-6',
      openai: 'gpt-5.2',
      gemini: 'gemini-2.5-flash',
      xai: 'grok-4-1-fast-reasoning',
      perplexity: 'sonar-pro',
      mistral: 'mistral-large-latest',
      cohere: 'command-a-03-2025',
      huggingface: 'Llama-3.3-70B'
    };
    return models[provider] || '';
  }

  showEmpty() {
    this.container.html('<p style="margin:0;color:var(--muted);font-size:0.8rem;">No provider statistics available.</p>');
  }

  destroy() {
    if (this.statsWrap) this.statsWrap.remove();
    if (this.svg) this.svg.remove();
  }
}

window.Sidebar = Sidebar;
