/* Keep the first submission usable and prevent accidental duplicate clicks. */
document.addEventListener('DOMContentLoaded', () => {
  const form = document.querySelector('#prediction-form');
  if (form) {
    const button = document.querySelector('#predict-button');
    form.addEventListener('submit', () => {
      if (!form.checkValidity()) return;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.querySelector('span').textContent = 'Analysing your application…';
    });
    window.addEventListener('pageshow', () => {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.querySelector('span').textContent = 'Generate prediction';
    });
    const errors = document.querySelector('.form-error-summary');
    if (errors) errors.focus();
  }
});
