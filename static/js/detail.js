class StockDetail {
  constructor(containerSelector, options = {}) {
    this.container = d3.select(containerSelector);
    this.options = {
      width: options.width || 840,
      height: options.height || 400,
      margin: { top: 26, right: 28, bottom: 40, left: 60 },
      ...options
    };

    this.colors = this.readColors();
    this.svg = null;
    this.chart = null;
    this.tooltip = null;
    this.current = null;
    this.scales = { x: null, y: null };

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
      flat: css.getPropertyValue('--flat').trim()
    };
  }

  init() {
    const { width, height, margin } = this.options;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    this.svg = this.container.append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .attr('role', 'img')
      .attr('tabindex', 0)
      .attr('aria-label', 'Stock price chart and prediction markers');

    this.chart = this.svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    this.chart.append('g').attr('class', 'grid-x').attr('transform', `translate(0,${innerH})`);
    this.chart.append('g').attr('class', 'grid-y');
    this.chart.append('path').attr('class', 'line-path');
    this.chart.append('g').attr('class', 'prediction-markers');
    this.chart.append('line').attr('class', 'focus-line').attr('stroke-dasharray', '4 4').attr('opacity', 0);
    this.chart.append('circle').attr('class', 'focus-dot').attr('r', 4).attr('opacity', 0);

    this.tooltip = this.container.append('div')
      .style('position', 'absolute')
      .style('pointer-events', 'none')
      .style('opacity', 0)
      .style('padding', '0.5rem 0.65rem')
      .style('border', `1px solid ${this.colors.line}`)
      .style('background', 'rgba(8, 14, 19, 0.95)')
      .style('border-radius', '8px')
      .style('font-size', '12px');
  }

  update(payload) {
    const historyRaw = payload?.price_history || payload?.history || [];
    if (!historyRaw.length) {
      this.showEmpty();
      return;
    }

    const history = historyRaw
      .map((d) => ({ date: new Date(d.timestamp || d.date), price: +d.price }))
      .filter((d) => Number.isFinite(d.date.getTime()) && Number.isFinite(d.price));

    if (!history.length) {
      this.showEmpty();
      return;
    }

    const predictions = (payload.predictions || []).map((p) => ({
      date: new Date(p.prediction_time || p.date),
      direction: p.predicted_direction || p.prediction || 'neutral',
      confidence: +p.confidence || 0,
      provider: p.provider || '',
      price: Number.isFinite(+p.initial_price) ? +p.initial_price : null
    }));

    this.current = { symbol: payload.symbol || '', history, predictions };

    const { width, height, margin } = this.options;
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    this.scales.x = d3.scaleTime().domain(d3.extent(history, (d) => d.date)).range([0, innerW]).nice();
    const [minPrice, maxPrice] = d3.extent(history, (d) => d.price);
    const pad = (maxPrice - minPrice || 1) * 0.14;
    this.scales.y = d3.scaleLinear().domain([minPrice - pad, maxPrice + pad]).range([innerH, 0]).nice();

    this.chart.select('.grid-x')
      .call(d3.axisBottom(this.scales.x).ticks(6).tickFormat(d3.timeFormat('%b %d')))
      .selectAll('text').attr('fill', this.colors.muted).style('font-size', '11px');

    this.chart.select('.grid-y')
      .call(d3.axisLeft(this.scales.y).ticks(5).tickFormat((n) => `$${n.toFixed(2)}`))
      .selectAll('text').attr('fill', this.colors.muted).style('font-size', '11px');

    this.chart.selectAll('.grid-x path, .grid-x line, .grid-y path, .grid-y line').attr('stroke', this.colors.line);

    const line = d3.line().x((d) => this.scales.x(d.date)).y((d) => this.scales.y(d.price)).curve(d3.curveMonotoneX);
    this.chart.select('.line-path')
      .datum(history)
      .attr('fill', 'none')
      .attr('stroke', this.colors.up)
      .attr('stroke-width', 2)
      .transition().duration(420)
      .attr('d', line);

    const marks = this.chart.select('.prediction-markers').selectAll('g.marker').data(predictions, (d) => `${d.provider}-${+d.date}`);
    const marksEnter = marks.enter().append('g').attr('class', 'marker').style('opacity', 0);
    marksEnter.append('circle').attr('class', 'marker-hit').attr('r', 18).attr('fill', 'transparent');
    marksEnter.append('circle').attr('class', 'marker-dot').attr('r', 5);

    const marksMerged = marksEnter.merge(marks)
      .attr('transform', (d) => `translate(${this.scales.x(d.date)},${this.scales.y(d.price ?? history.at(-1).price)})`)
      .on('mouseenter', (event, d) => this.showPredictionTip(event, d))
      .on('mouseleave', () => this.hideTooltip());

    marksMerged.select('.marker-dot')
      .attr('fill', (d) => this.predictionColor(d.direction))
      .attr('stroke', '#081017')
      .attr('stroke-width', 1.6)
      .attr('opacity', (d) => Math.max(0.35, d.confidence));

    marksEnter.transition().duration(300).style('opacity', 1);
    marks.exit().remove();

    this.installHover(history, innerW, innerH);
  }

  installHover(history, innerW, innerH) {
    this.chart.selectAll('rect.hover-layer').remove();

    this.chart.append('rect')
      .attr('class', 'hover-layer')
      .attr('width', innerW)
      .attr('height', innerH)
      .attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const [x] = d3.pointer(event);
        const date = this.scales.x.invert(x);
        const bisect = d3.bisector((d) => d.date).left;
        const idx = bisect(history, date, 1);
        const left = history[idx - 1];
        const right = history[idx];
        const point = !right ? left : date - left.date > right.date - date ? right : left;

        const px = this.scales.x(point.date);
        const py = this.scales.y(point.price);

        this.chart.select('.focus-line')
          .attr('x1', px).attr('x2', px)
          .attr('y1', 0).attr('y2', innerH)
          .attr('stroke', this.colors.muted)
          .attr('opacity', 0.6);

        this.chart.select('.focus-dot')
          .attr('cx', px).attr('cy', py)
          .attr('fill', this.colors.up)
          .attr('stroke', '#fff')
          .attr('stroke-width', 1.5)
          .attr('opacity', 1);

        this.showPriceTip(event, point);
      })
      .on('mouseleave', () => this.hideTooltip());
  }

  predictionColor(direction) {
    if (direction === 'up') return this.colors.up;
    if (direction === 'down') return this.colors.down;
    return this.colors.flat;
  }

  showPriceTip(event, point) {
    if (!this.current) return;
    const html = `<strong>${this.current.symbol}</strong><br>${d3.timeFormat('%b %d, %Y')(point.date)}<br>$${point.price.toFixed(2)}`;
    this.tooltip.html(html)
      .style('left', `${event.pageX + 12}px`)
      .style('top', `${event.pageY - 12}px`)
      .style('opacity', 1);
  }

  showPredictionTip(event, prediction) {
    const html = `<strong>${prediction.provider || 'Model'}</strong><br>${prediction.direction.toUpperCase()} · ${(prediction.confidence * 100).toFixed(0)}%`;
    this.tooltip.html(html)
      .style('left', `${event.pageX + 12}px`)
      .style('top', `${event.pageY - 12}px`)
      .style('opacity', 1);
  }

  hideTooltip() {
    this.tooltip.style('opacity', 0);
    this.chart.select('.focus-line').attr('opacity', 0);
    this.chart.select('.focus-dot').attr('opacity', 0);
  }

  showEmpty() {
    this.container.selectAll('*').remove();
    this.container.append('p').style('margin', '0').style('color', this.colors.muted).text('Select a stock tile to inspect chart details.');
  }

  destroy() {
    if (this.svg) this.svg.remove();
    if (this.tooltip) this.tooltip.remove();
  }
}

window.StockDetail = StockDetail;
