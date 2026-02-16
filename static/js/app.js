// Foresight Dashboard - Main Application

console.log('Foresight Dashboard initializing...');

// Check API health
fetch('/api/current')
    .then(r => r.json())
    .then(data => console.log('API Status:', data))
    .catch(err => console.error('API Error:', err));
