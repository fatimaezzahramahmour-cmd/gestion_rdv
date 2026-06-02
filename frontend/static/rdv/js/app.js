/**
 * Gestion RDV - Frontend Enhancements
 * Smooth UX & form feedback
 */

document.addEventListener('DOMContentLoaded', function() {
  // Form validation feedback
  const forms = document.querySelectorAll('form');
  forms.forEach(function(form) {
    form.addEventListener('submit', function() {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn && !submitBtn.disabled) {
        submitBtn.disabled = true;
        submitBtn.dataset.originalText = submitBtn.textContent;
        submitBtn.textContent = submitBtn.dataset.loadingText || 'Chargement...';
      }
    });
  });

  // Add focus styling to inputs
  const inputs = document.querySelectorAll('.form-control, input[type="text"], input[type="email"], input[type="password"], input[type="datetime-local"], textarea');
  inputs.forEach(function(input) {
    input.classList.add('form-custom');
  });

  // Auto-hide alerts after 5 seconds
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(function(alert) {
    setTimeout(function() {
      alert.style.transition = 'opacity 0.3s ease';
      alert.style.opacity = '0';
      setTimeout(function() { alert.remove(); }, 300);
    }, 5000);
  });
});
