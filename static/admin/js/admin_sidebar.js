/**
 * KHATA Platform Admin — sidebar accordion (matches dashboard sidebar behavior).
 *
 * Loaded once from <head> (see base.html) so Turbo Drive never re-executes
 * it across navigations — only the `turbo:load` listener below re-runs
 * init against the fresh #jazzy-navigation Turbo just swapped in. Because
 * of that, jQuery must be looked up lazily inside initKhataSidebar rather
 * than captured as a closure argument at parse time: this script's own
 * <script> tag loads in <head>, before jQuery's <script> tag (still in
 * <body>) has run.
 */
(function () {
  'use strict';

  function injectAnalyticsLink($) {
    // The dashboard now lives at /admin/ itself, so this just links home.
    var $nav = $('#jazzy-navigation');
    if (!$nav.length || $nav.find('a[href="/admin/"]').length) return;

    var path = window.location.pathname.replace(/\/$/, '');
    var isActive = path === '' || path === '/admin';
    var $item = $(
      '<li class="nav-item">' +
        '<a href="/admin/" class="nav-link' + (isActive ? ' active' : '') + '">' +
          '<i class="nav-icon fas fa-chart-line"></i>' +
          '<p>Dashboard</p>' +
        '</a>' +
      '</li>'
    );
    $nav.children('.nav-item').first().after($item);
  }

  function initKhataSidebar() {
    var $ = window.jQuery;
    if (!$) return;

    var $nav = $('#jazzy-navigation');
    if (!$nav.length) return;

    injectAnalyticsLink($);

    $nav.attr('data-accordion', 'true');

    $nav.children('.nav-item.has-treeview').each(function () {
      var $item = $(this);
      var $submenu = $item.children('.nav-treeview');
      if (!$item.hasClass('menu-open')) {
        $submenu.hide();
      }
    });

    $nav[0].addEventListener(
      'click',
      function (event) {
        var link = event.target.closest('.nav-item.has-treeview > a.nav-link');
        if (!link || !$nav[0].contains(link)) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        var $item = $(link).parent();
        var $submenu = $item.children('.nav-treeview');
        var isOpen = $item.hasClass('menu-open');

        $nav.children('.nav-item.has-treeview').not($item).each(function () {
          $(this).removeClass('menu-open menu-is-opening');
          $(this).children('.nav-treeview').stop(true, true).slideUp(200);
        });

        if (isOpen) {
          $item.removeClass('menu-open menu-is-opening');
          $submenu.stop(true, true).slideUp(200);
        } else {
          $item.addClass('menu-open menu-is-opening');
          $submenu.stop(true, true).slideDown(200);
        }
      },
      true
    );
  }

  // `turbo:load` fires after the initial page load too, not just
  // subsequent visits, so this is the only listener needed.
  document.addEventListener('turbo:load', initKhataSidebar);
})();
