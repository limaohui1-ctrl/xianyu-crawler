/* ── ACS 资料采集助手 — App Logic ── */
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
    body.classList.toggle('dark');
    if(body.classList.contains('dark')){
      icon.textContent = '☾';
      label.textContent = '暗色';
    } else {
      icon.textContent = '☀';
      label.textContent = '亮色';
    }
  };

  // ── Export Report ──
  window.exportReport = function(){
    var data = {
      version: 'ACS v1.0.0-sandbox',
      app: '资料采集助手',
      exported_at: new Date().toISOString(),
      total_entries: 86,
      success: 86,
      failed: 0,
      site: 'books.toscrape.com',
      completeness: '63.5%'
    };
    var blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '资料导出_' + new Date().toISOString().slice(0,10) + '.json';
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

  // ── Default dark mode ──
  document.body.classList.add('dark');

})();
