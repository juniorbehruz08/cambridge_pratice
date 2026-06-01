(function () {
    'use strict';

    var dataEl = document.getElementById('past-results-data');
    if (!dataEl) return;

    var panels;
    try {
        panels = JSON.parse(dataEl.textContent);
    } catch (e) {
        return;
    }
    if (!Array.isArray(panels) || panels.length === 0) return;

    if (typeof Chart === 'undefined') return;

    Chart.defaults.font.family = 'Arial, Helvetica, sans-serif';

    function initChart(canvasId, labels, values, maxVal, lineColor, areaColor, unitLabel) {
        var canvas = document.getElementById(canvasId);
        if (!canvas || !labels || labels.length === 0) return;

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: unitLabel,
                    data: values,
                    borderColor: lineColor,
                    backgroundColor: areaColor,
                    borderWidth: 2.5,
                    pointBackgroundColor: lineColor,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2.5,
                    pointRadius: labels.length === 1 ? 7 : 4.5,
                    pointHoverRadius: 8,
                    tension: 0.35,
                    fill: true,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 600, easing: 'easeInOutQuart' },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1e293b',
                        titleColor: '#94a3b8',
                        bodyColor: '#f8fafc',
                        padding: 10,
                        cornerRadius: 8,
                        displayColors: false,
                        callbacks: {
                            label: function (ctx) {
                                var suffix = unitLabel === 'Band' ? '' : ' / 40';
                                return ' ' + ctx.parsed.y + suffix;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            maxRotation: 45,
                            font: { size: 10, weight: '700' },
                            color: '#94a3b8',
                        },
                    },
                    y: {
                        min: 0,
                        max: maxVal,
                        border: { display: false },
                        grid: { color: '#e2e8f0', tickLength: 0 },
                        ticks: {
                            stepSize: maxVal === 9 ? 1 : 10,
                            font: { size: 10, weight: '700' },
                            color: '#94a3b8',
                            padding: 6,
                        },
                    },
                },
            },
        });
    }

    panels.forEach(function (panel) {
        initChart(
            'chart-' + panel.section + '-band',
            panel.band.labels, panel.band.values, 9,
            '#2563eb', 'rgba(37,99,235,0.1)', 'Band'
        );
        initChart(
            'chart-' + panel.section + '-score',
            panel.score.labels, panel.score.values, 40,
            '#16a34a', 'rgba(22,163,74,0.1)', 'Score'
        );
    });
}());
