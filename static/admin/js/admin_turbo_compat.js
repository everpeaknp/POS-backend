/**
 * KHATA Admin — Turbo Drive compatibility shim.
 *
 * Turbo Drive swaps <body> content on navigation instead of doing a full
 * page load, so third-party scripts that only run once on
 * DOMContentLoaded / jQuery "ready" (Django's select2 autocomplete,
 * DateTimeShortcuts calendar/clock widgets, inline formset add/remove
 * buttons) never re-run for the new page. This re-triggers each of them
 * on every `turbo:load`, safely, against the fresh DOM Turbo just
 * swapped in (never against stale/removed nodes).
 */
(function () {
  'use strict';

  function reinitDateTimeShortcuts() {
    if (window.DateTimeShortcuts && typeof DateTimeShortcuts.init === 'function') {
      try {
        DateTimeShortcuts.init();
      } catch (e) {
        /* no date/time widgets on this page */
      }
    }
  }

  function reinitSelect2Autocomplete() {
    var djangoJQuery = window.django && window.django.jQuery;
    if (!djangoJQuery || !djangoJQuery.fn.djangoAdminSelect2) return;
    try {
      djangoJQuery('.admin-autocomplete')
        .not('[name*=__prefix__]')
        .not('.select2-hidden-accessible')
        .djangoAdminSelect2();
    } catch (e) {
      /* no autocomplete widgets on this page */
    }
  }

  function reinitInlineFormsets() {
    var djangoJQuery = window.django && window.django.jQuery;
    if (!djangoJQuery) return;
    try {
      djangoJQuery('.js-inline-admin-formset').each(function () {
        var $formset = djangoJQuery(this);
        var data = $formset.data();
        var inlineOptions = data.inlineFormset;
        if (!inlineOptions) return;
        var selector;
        if (data.inlineType === 'stacked' && djangoJQuery.fn.stackedFormset) {
          selector = inlineOptions.name + '-group .inline-related';
          djangoJQuery(selector).stackedFormset(selector, inlineOptions.options);
        } else if (data.inlineType === 'tabular' && djangoJQuery.fn.tabularFormset) {
          selector = inlineOptions.name + '-group .tabular.inline-related tbody:first > tr.form-row';
          djangoJQuery(selector).tabularFormset(selector, inlineOptions.options);
        }
      });
    } catch (e) {
      /* no inline formsets on this page */
    }
  }

  function reinitAll() {
    reinitDateTimeShortcuts();
    reinitSelect2Autocomplete();
    reinitInlineFormsets();
  }

  document.addEventListener('turbo:load', reinitAll);

  // Brand the Turbo progress bar to match the app's accent green instead
  // of Turbo's default blue.
  var style = document.createElement('style');
  style.textContent =
    '.turbo-progress-bar { background-color: #22c55e !important; height: 3px !important; }';
  document.head.appendChild(style);
})();
