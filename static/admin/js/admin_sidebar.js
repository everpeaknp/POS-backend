/**
 * KHATA Platform Admin — sidebar accordion (matches dashboard sidebar behavior).
 */
(function ($) {
  'use strict';

  function injectAnalyticsLink() {
    var $nav = $('#jazzy-navigation');
    if (!$nav.length || $nav.find('a[href="/admin/platform/"]').length) return;

    var path = window.location.pathname.replace(/\/$/, '');
    var isActive = path === '/admin/platform';
    var $item = $(
      '<li class="nav-item">' +
        '<a href="/admin/platform/" class="nav-link' + (isActive ? ' active' : '') + '">' +
          '<i class="nav-icon fas fa-chart-line"></i>' +
          '<p>Analytics</p>' +
        '</a>' +
      '</li>'
    );
    $nav.children('.nav-item').first().after($item);
  }

  function initKhataSidebar() {
    var $nav = $('#jazzy-navigation');
    if (!$nav.length) return;

    injectAnalyticsLink();

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

  $(initKhataSidebar);
})(jQuery);
