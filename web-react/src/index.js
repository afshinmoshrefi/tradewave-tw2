
import React from 'react';
import ReactDOM from 'react-dom';
import './components/styles/App.css';
import App from './components/App';
import ErrorBoundary from './components/ErrorBoundary';
import reportWebVitals from './reportWebVitals';


// this is the warning for divi - not sure why it happens but it is distracting in dev - remove it in production 2/1/2024
// didn't work
// const originalWarn = console.warn.bind(console.warn);
// console.warn = (text = '') => {
//   if (!text.includes('preloaded')) {
//     originalWarn(text);
//   }
// };

ReactDOM.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
  document.getElementById('root')
);


reportWebVitals();
