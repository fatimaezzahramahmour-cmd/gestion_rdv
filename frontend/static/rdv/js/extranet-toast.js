(function () {
  'use strict';

  var TYPE_MAP = {
    success: { bg: '#dcfce7', border: '#86efac', color: '#166534', icon: '✓' },
    error: { bg: '#fee2e2', border: '#fecaca', color: '#991b1b', icon: '!' },
    warning: { bg: '#fef3c7', border: '#fde68a', color: '#92400e', icon: '!' },
    info: { bg: '#e0f2fe', border: '#bae6fd', color: '#0c4a6e', icon: 'i' },
    debug: { bg: '#f1f5f9', border: '#e2e8f0', color: '#475569', icon: 'i' },
  };

  function normalizeType(tags) {
    if (!tags) return 'info';
    if (tags.indexOf('error') !== -1) return 'error';
    if (tags.indexOf('warning') !== -1) return 'warning';
    if (tags.indexOf('success') !== -1) return 'success';
    return 'info';
  }

  function ensureContainer() {
    var el = document.getElementById('extranetToastContainer');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'extranetToastContainer';
    el.className = 'extranet-toast-container';
    el.setAttribute('aria-live', 'polite');
    el.setAttribute('aria-atomic', 'true');
    document.body.appendChild(el);
    return el;
  }

  function showExtranetToast(message, type) {
    if (!message) return;
    var kind = TYPE_MAP[type] || TYPE_MAP.info;
    var container = ensureContainer();
    var toast = document.createElement('div');
    toast.className = 'extranet-toast extranet-toast--show';
    toast.setAttribute('role', 'alert');
    toast.style.background = kind.bg;
    toast.style.borderColor = kind.border;
    toast.style.color = kind.color;

    var icon = document.createElement('span');
    icon.className = 'extranet-toast-icon';
    icon.textContent = kind.icon;

    var body = document.createElement('span');
    body.className = 'extranet-toast-text';
    body.textContent = message;

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'extranet-toast-close';
    close.setAttribute('aria-label', 'Fermer');
    close.innerHTML = '&times;';

    toast.appendChild(icon);
    toast.appendChild(body);
    toast.appendChild(close);
    container.appendChild(toast);

    function dismiss() {
      toast.classList.remove('extranet-toast--show');
      toast.classList.add('extranet-toast--hide');
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 280);
    }

    close.addEventListener('click', dismiss);
    setTimeout(dismiss, 6000);
  }

  window.showExtranetToast = showExtranetToast;

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-extranet-toast]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        showExtranetToast(
          btn.getAttribute('data-extranet-toast'),
          btn.getAttribute('data-toast-type') || 'warning'
        );
      });
    });

    var flashNodes = document.querySelectorAll('[data-flash-text]');
    flashNodes.forEach(function (node) {
      showExtranetToast(
        node.getAttribute('data-flash-text'),
        normalizeType(node.getAttribute('data-flash-tags'))
      );
    });
    var flashRoot = document.getElementById('extranet-flash-messages');
    if (flashRoot) flashRoot.remove();
  });
})();
