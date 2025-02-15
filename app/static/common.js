"use strict";

let previous_adapt_ts = null;
function adapt_to_window_size() {
    window.requestAnimationFrame(function (ts) {
        if (ts === previous_adapt_ts)
            return;

        document.documentElement.style.setProperty('--unit', `${0.01 * window.visualViewport.height}px`);
        previous_adapt_ts = ts;
    });
}
adapt_to_window_size();
window.visualViewport.addEventListener('resize', adapt_to_window_size);

// Theme handling
const themeToggle = document.getElementById('themeToggle');

function setTheme(theme) {
  document.body.style.colorScheme = theme;
  localStorage.setItem('theme', theme);
  document.getElementById('sun-icon').style.display = theme === 'dark' ? 'none' : 'block';
  document.getElementById('moon-icon').style.display = theme === 'dark' ? 'block' : 'none';
}

// Check for saved theme preference, otherwise use system preference
const savedTheme = localStorage.getItem('theme');
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const defaultTheme = savedTheme || (prefersDark ? 'dark' : 'light');

// Set initial theme
setTheme(defaultTheme);

// Toggle theme when button is clicked
themeToggle.addEventListener('click', () => {
  const currentTheme = document.body.style.colorScheme;
  setTheme(currentTheme === 'dark' ? 'light' : 'dark');
});