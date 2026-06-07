import React from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

// Ensure dark class is always present — design is dark-mode-only
document.documentElement.classList.add('dark');

const root = createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
