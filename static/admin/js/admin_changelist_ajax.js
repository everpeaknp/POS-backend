/**
 * KHATA Admin — fragment-only changelist filtering/sorting/pagination.
 *
 * Turbo Drive already gives whole-page soft navigation, but a filter click
 * or a page-2 click on a changelist doesn't need the sidebar/header
 * re-rendered — only the results (#changelist) and the filter toolbar's
 * result count (#change-list-filters) actually change. This wires those
 * same-path GET links/forms to htmx instead, swapping just those two
 * pieces out of the normally-rendered full-page response (via
 * hx-select / hx-select-oob — no separate fragment view needed).
 *
 * Turbo's own global click/submit interception is explicitly disabled
 * (data-turbo="false") on every element htmx takes over, so the two
 * libraries never race for the same click.
 */
(function () {
  'use strict';

  var CL_ID = 'changelist';
  var FILTERS_ID = 'change-list-filters';

  function samePath(href) {
    try {
      var url = new URL(href, window.location.origin);
      if (url.origin !== window.location.origin) return false;
      var here = window.location.pathname.replace(/\/$/, '');
      var there = url.pathname.replace(/\/$/, '');
      return here === there;
    } catch (e) {
      return false;
    }
  }

  function applyAjaxAttrs(el) {
    el.setAttribute('data-turbo', 'false');
    el.setAttribute('hx-target', '#' + CL_ID);
    el.setAttribute('hx-select', '#' + CL_ID);
    el.setAttribute('hx-select-oob', '#' + FILTERS_ID);
    el.setAttribute('hx-swap', 'outerHTML show:none');
    el.setAttribute('hx-push-url', 'true');
    el.setAttribute('hx-indicator', '#' + CL_ID);
  }

  function wireLink(a) {
    if (a.hasAttribute('data-cl-ajax')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || !samePath(href)) return;
    a.setAttribute('data-cl-ajax', '1');
    a.setAttribute('hx-get', href);
    applyAjaxAttrs(a);
    window.htmx.process(a);
  }

  function wireForm(form) {
    if (form.hasAttribute('data-cl-ajax')) return;
    form.setAttribute('data-cl-ajax', '1');
    form.setAttribute('hx-get', window.location.pathname);
    applyAjaxAttrs(form);
    window.htmx.process(form);
  }

  function reinitChangelistWidgets() {
    var $ = window.jQuery;
    if (!$ || !$.fn.select2) return;

    $('.search-filter').each(function () {
      var $f = $(this);
      if ($f.hasClass('select2-hidden-accessible')) return;
      $f.on('change', function () {
        var name = $f.find('option:selected').data('name');
        if (name) $f.attr('name', name);
        else $f.removeAttr('name');
      });
      $f.trigger('change');
      var minLen = (window.filterInputLength && window.filterInputLength[$f.data('name')]) || window.filterInputLengthDefault || 0;
      $f.select2({ minimumInputLength: minLen });
    });

    var $actions = $('.actions select');
    if ($actions.length && !$actions.hasClass('select2-hidden-accessible')) {
      $actions.addClass('form-control').select2({ width: 'element' });
    }
  }

  function wireAll() {
    if (typeof window.htmx === 'undefined') return;
    var cl = document.getElementById(CL_ID);
    if (!cl) return;

    var filters = document.getElementById(FILTERS_ID);
    if (filters) {
      var form = document.getElementById('changelist-search');
      if (form) wireForm(form);
      filters.querySelectorAll('a[href]').forEach(wireLink);
    }

    cl.querySelectorAll('a[href]').forEach(wireLink);
  }

  document.addEventListener('turbo:load', wireAll);

  // Runs after every htmx-driven changelist swap: the fresh HTML pulled
  // out of the response has none of our hx-*/data-turbo attributes (those
  // only exist on the elements we mutated client-side), and jazzmin's own
  // per-page change_list.js — which normally select2-ifies the filter
  // dropdowns — never re-runs here since it lives outside the swapped
  // fragment (near the end of <body>, not inside #changelist).
  document.addEventListener('htmx:afterSettle', function () {
    wireAll();
    reinitChangelistWidgets();
  });
})();
