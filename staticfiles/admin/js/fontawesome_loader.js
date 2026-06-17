/**
 * Font Awesome Loader for Jazzmin Admin
 * Loads Font Awesome 5 icons from CDN
 */

(function() {
    // Check if Font Awesome is already loaded
    if (typeof FontAwesome !== 'undefined') {
        console.log('Font Awesome already loaded');
        return;
    }

    // Create link element for Font Awesome CSS
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css';
    link.integrity = 'sha512-1ycn6IcaQQ40/MKBW2W4Rhis/DbILU74C1vSrLJxCq57o941Ym01SwNsOMqvEBFlcgUa6xLiPY/NS5R+E6ztJQ==';
    link.crossOrigin = 'anonymous';
    link.referrerPolicy = 'no-referrer';
    
    // Append to head
    document.head.appendChild(link);
    
    console.log('Font Awesome 5 loaded from CDN');
})();
