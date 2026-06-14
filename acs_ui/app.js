/* ── ACS Console: App Logic ── */
(function(){
  'use strict';

  // ── Clock ──
  function updateClock(){
    var now = new Date();
    var s = now.toISOString().replace('T',' ').slice(0,19);
    var el = document.getElementById('clock');
    if(el) el.textContent = s;
  }
  updateClock();
  setInterval(updateClock, 1000);

  // ── Page Switching ──
  window.switchPage = function(name){
    document.querySelectorAll('.page').forEach(function(p){ p.classList.remove('active'); });
    document.querySelectorAll('.nav-item').forEach(function(n){ n.classList.remove('active'); });
    var page = document.getElementById('page-' + name);
    if(page) page.classList.add('active');
    var nav = document.querySelector('[data-page="' + name + '"]');
    if(nav) nav.classList.add('active');
  };

  // ── Theme Toggle ──
  window.toggleTheme = function(){
    var body = document.body;
    var icon = document.getElementById('theme-icon');
    var label = document.getElementById('theme-label');
    body.classList.toggle('light');
    if(body.classList.contains('light')){
      icon.textContent = '☀';
      label.textContent = '亮色';
    } else {
      icon.textContent = '☾';
      label.textContent = '暗色';
    }
  };

  // ── Export Report ──
  window.exportReport = function(){
    var data = {
      version: 'ACS v1.0.0-sandbox',
      acs_mode: 'shadow',
      real_phase10: false,
      sandbox_canary: 'completed',
      test_readiness: 'READY (books.toscrape.com 352/100%/63.5%)',
      real_readiness: 'NOT_READY',
      tests: '529/529 pytest, 15/15 health, 11/11 release',
      exported_at: new Date().toISOString()
    };
    var blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'acs_status_' + new Date().toISOString().slice(0,10) + '.json';
    a.click();
  };

  // ── Toast Notification ──
  window.showToast = function(message) {
    var toast = document.getElementById('toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'toast';
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('show');
    setTimeout(function(){ toast.classList.remove('show'); }, 2200);
  };

})();
