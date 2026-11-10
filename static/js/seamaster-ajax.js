/**
 * Global AJAX & Toast Notification Engine
 * Provides seamless, zero-reload asynchronous interactions across all pages.
 */

(function() {
  'use strict';

  // =========================================================================
  // 1. Toast Notification System
  // =========================================================================

  function getOrCreateToastContainer() {
    let container = document.getElementById('sm-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'sm-toast-container';
      container.className = 'sm-toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  window.showToast = function(message, type = 'success', duration = 3200) {
    const container = getOrCreateToastContainer();
    const toast = document.createElement('div');
    toast.className = `sm-toast sm-toast-${type}`;

    let iconClass = 'fa-check-circle';
    if (type === 'error' || type === 'danger') iconClass = 'fa-times-circle';
    else if (type === 'warning') iconClass = 'fa-exclamation-triangle';
    else if (type === 'info') iconClass = 'fa-info-circle';

    toast.innerHTML = `
      <div class="toast-icon"><i class="fas ${iconClass}"></i></div>
      <div class="toast-message">${message}</div>
      <button type="button" class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;

    container.appendChild(toast);

    // Auto remove after duration
    setTimeout(() => {
      toast.classList.add('fade-out');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  };

  // =========================================================================
  // 2. CSRF Token & Helper Fetch
  // =========================================================================

  function getCsrfToken() {
    // 1. From meta tag
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;

    // 2. From hidden form inputs
    const input = document.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;

    // 3. From cookie
    const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  window.smFetch = function(url, options = {}) {
    options.headers = options.headers || {};
    options.headers['X-Requested-With'] = 'XMLHttpRequest';
    options.headers['Accept'] = 'application/json';

    const csrf = getCsrfToken();
    if (csrf) {
      options.headers['X-CSRFToken'] = csrf;
    }

    return fetch(url, options).then(async (response) => {
      let data = {};
      try {
        data = await response.json();
      } catch (e) {
        data = { status: response.ok ? 'ok' : 'error' };
      }
      if (!response.ok) {
        throw new Error(data.message || 'خطا در برقراری ارتباط با سرور.');
      }
      return data;
    });
  };

  // =========================================================================
  // 3. Universal Form & Action Interceptors
  // =========================================================================

  document.addEventListener('DOMContentLoaded', function() {

    // A. Intercept Task Checkbox Toggles (e.g. on /today and /tasks/dashboard)
    document.addEventListener('change', function(e) {
      const checkbox = e.target.closest('.ajax-task-check, .task-checkbox');
      if (!checkbox) return;

      const form = checkbox.closest('form');
      const actionUrl = form ? form.action : checkbox.dataset.action;
      if (!actionUrl) return;

      const taskItem = checkbox.closest('.operational-task-item, .task-card-item, tr');
      const label = taskItem ? taskItem.querySelector('.task-title, .task-name, label') : null;

      // Optimistic UI toggle
      const isChecked = checkbox.checked;
      if (taskItem) {
        taskItem.classList.toggle('task-completed', isChecked);
        if (label) label.style.textDecoration = isChecked ? 'line-through' : 'none';
      }

      const formData = new FormData();
      const csrf = getCsrfToken();
      if (csrf) formData.append('csrf_token', csrf);

      smFetch(actionUrl, {
        method: 'POST',
        body: formData
      })
      .then((data) => {
        showToast(data.message || (isChecked ? 'وظیفه به انجام شده تغییر یافت ✓' : 'وظیفه در انتظار قرار گرفت.'), 'success');
      })
      .catch((err) => {
        // Revert UI on failure
        checkbox.checked = !isChecked;
        if (taskItem) {
          taskItem.classList.toggle('task-completed', !isChecked);
          if (label) label.style.textDecoration = !isChecked ? 'line-through' : 'none';
        }
        showToast(err.message || 'خطا در ثبت وضعیت وظیفه', 'error');
      });
    });

    // B. Intercept Generic AJAX Delete Actions (e.g. on /meetings, /users, /tasks)
    document.addEventListener('submit', function(e) {
      const form = e.target.closest('form[data-ajax-delete="true"]');
      if (!form) return;

      e.preventDefault();
      const confirmMsg = form.getAttribute('data-confirm') || 'آیا از حذف این مورد اطمینان دارید؟';
      if (!window.confirm(confirmMsg)) return;

      const targetSelector = form.getAttribute('data-target-remove');
      const targetElement = targetSelector ? document.querySelector(targetSelector) : form.closest('tr, .card, .agenda-card, .meeting-card, .user-row');

      const submitBtn = form.querySelector('button[type="submit"]');
      const originalHtml = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        submitBtn.disabled = true;
      }

      const formData = new FormData(form);
      if (!formData.has('csrf_token')) {
        const csrf = getCsrfToken();
        if (csrf) formData.append('csrf_token', csrf);
      }

      smFetch(form.action, {
        method: 'POST',
        body: formData
      })
      .then((data) => {
        if (targetElement) {
          targetElement.style.transition = 'all 0.35s ease';
          targetElement.style.opacity = '0';
          targetElement.style.transform = 'scale(0.95) translateY(-10px)';
          setTimeout(() => targetElement.remove(), 350);
        }
        showToast(data.message || 'مورد با موفقیت حذف شد ✓', 'success');
      })
      .catch((err) => {
        if (submitBtn) {
          submitBtn.innerHTML = originalHtml;
          submitBtn.disabled = false;
        }
        showToast(err.message || 'خطا در حذف مورد', 'error');
      });
    });

    // C. Intercept Quick Form Submissions with [data-ajax="true"]
    document.addEventListener('submit', function(e) {
      const form = e.target.closest('form[data-ajax="true"]');
      if (!form) return;

      e.preventDefault();
      const submitBtn = form.querySelector('button[type="submit"]');
      const originalHtml = submitBtn ? submitBtn.innerHTML : '';
      if (submitBtn) {
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> در حال ارسال...';
        submitBtn.disabled = true;
      }

      const formData = new FormData(form);
      if (!formData.has('csrf_token')) {
        const csrf = getCsrfToken();
        if (csrf) formData.append('csrf_token', csrf);
      }

      smFetch(form.action, {
        method: form.method || 'POST',
        body: formData
      })
      .then((data) => {
        if (submitBtn) {
          submitBtn.innerHTML = originalHtml;
          submitBtn.disabled = false;
        }
        showToast(data.message || 'اطلاعات با موفقیت ثبت شد ✓', 'success');
        
        // Reset form if requested
        if (form.getAttribute('data-reset-on-success') !== 'false') {
          form.reset();
        }

        // Trigger custom event
        const event = new CustomEvent('sm:form-success', { detail: { form, data } });
        document.dispatchEvent(event);
      })
      .catch((err) => {
        if (submitBtn) {
          submitBtn.innerHTML = originalHtml;
          submitBtn.disabled = false;
        }
        showToast(err.message || 'خطا در ثبت اطلاعات', 'error');
      });
    });

  });

})();
