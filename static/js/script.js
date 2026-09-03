document.addEventListener('DOMContentLoaded', () => {
    // Only initialize charts if we are on the dashboard
    const pieCanvas = document.getElementById('performancePieChart');
    const barCanvas = document.getElementById('marksBarChart');

    if (pieCanvas && barCanvas) {
        fetchChartData();
    }
});

async function fetchChartData() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) throw new Error('Failed to fetch data');
        const data = await response.json();
        
        initPieChart(data.pie_chart);
        initBarChart(data.bar_chart);
    } catch (error) {
        console.error('Error loading chart data:', error);
    }
}

function initPieChart(data) {
    const ctx = document.getElementById('performancePieChart').getContext('2d');
    
    // Map colors based on AI Prediction labels to match CSS theme
    const colors = data.labels.map(label => {
        if (label === 'Excellent') return '#10b981'; // Success green
        if (label === 'Good') return '#3b82f6'; // Primary blue
        if (label === 'Average') return '#f59e0b'; // Warning yellow
        if (label === 'Needs Improvement') return '#ef4444'; // Danger red
        return '#94a3b8'; // Fallback gray
    });

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.data,
                backgroundColor: colors,
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#f8fafc', font: { family: 'Inter' } }
                }
            },
            cutout: '70%'
        }
    });
}

function initBarChart(data) {
    const ctx = document.getElementById('marksBarChart').getContext('2d');
    
    // Create gradient for bars
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.8)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.2)');

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Marks (%)',
                data: data.data,
                backgroundColor: gradient,
                borderRadius: 6,
                borderSkipped: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}
