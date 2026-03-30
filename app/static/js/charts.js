/* TGMA Platform — Chart.js defaults and helpers */

// Set global Chart.js defaults
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.font.size = 13;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.padding = 15;
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
}
