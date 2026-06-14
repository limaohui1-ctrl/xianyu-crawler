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

  // ── Provider Change ──
  window.onProviderChange = function(){
    var p = document.getElementById('provider_select').value;
    var descs = {
      'mock': '使用内置演示数据测试发现流程。',
      'import-file': '从 CSV/JSON/TXT/Markdown 文件导入 URL 列表。',
      'sitemap': '从公开 sitemap.xml 自动发现所有页面 URL。',
      'rss': '从公开 RSS/Atom feed 提取文章链接。'
    };
    document.getElementById('provider_desc').textContent = descs[p] || '';
    ['mock','import','sitemap','rss'].forEach(function(k){
      var el = document.getElementById('inputs_'+k);
      if(el) el.style.display = (k === p) ? '' : 'none';
    });
  };

  // ── Run Discovery ──
  window.runDiscovery = function(){
    var p = document.getElementById('provider_select').value;
    var topic = '', keywords = '', pathOrUrl = '';

    if(p === 'mock'){
      topic = document.getElementById('topic_mock').value || '园区废气治理案例';
      keywords = document.getElementById('keywords_mock').value || 'VOCs,活性炭,整改报告';
    } else if(p === 'import-file'){
      pathOrUrl = document.getElementById('import_path').value || 'search_results.csv';
      topic = document.getElementById('topic_import').value || '导入资料';
      keywords = document.getElementById('keywords_import').value || '';
    } else if(p === 'sitemap'){
      pathOrUrl = document.getElementById('sitemap_url').value || 'https://example.com/sitemap.xml';
      topic = document.getElementById('topic_sm').value || 'Sitemap资料';
      keywords = document.getElementById('keywords_sm').value || '';
    } else if(p === 'rss'){
      pathOrUrl = document.getElementById('feed_url').value || 'https://example.com/feed.xml';
      topic = document.getElementById('topic_rss').value || 'RSS资料';
      keywords = document.getElementById('keywords_rss').value || '';
    }

    // Build CLI command
    var cmd = 'D:/Python312/python.exe -m acs.discovery.discovery_cli';
    cmd += ' --provider ' + p;
    if(topic) cmd += ' --topic "' + topic + '"';
    if(keywords) cmd += ' --keywords "' + keywords + '"';
    if(p === 'import-file') cmd += ' --input "' + pathOrUrl + '"';
    if(p === 'sitemap') cmd += ' --sitemap-url "' + pathOrUrl + '"';
    if(p === 'rss') cmd += ' --feed-url "' + pathOrUrl + '"';
    cmd += ' --limit 20 --auto-select';
    cmd += '\n# 生成 selected_urls.txt 后执行采集:';
    cmd += '\nD:/Python312/python.exe -m acs.scripts.run_shadow_batch --urls acs_data/discovery/selected_urls.txt --site-id discovery_task --max-urls 20 --rate-limit 0.3';

    var cmdBox = document.getElementById('discovery_cmd');
    cmdBox.style.display = 'block';
    cmdBox.innerHTML = '<strong>请在终端运行：</strong><br><br>' + cmd.replace(/\n/g,'<br>').replace(/ /g,'&nbsp;');

    // Update candidate page with context
    document.getElementById('candidate_total').textContent = '6';
    document.getElementById('provider_label').textContent = '(' + ({mock:'Mock演示', 'import-file':'导入文件', sitemap:'Sitemap', rss:'RSS'})[p] + ')';

    switchPage('candidates');
    showToast('已生成发现命令。候选来源需用户确认后才能加入采集任务。');
  };

  // ── Select All Allowed ──
  window.selectAllAllowed = function(){
    var checks = document.querySelectorAll('#candidate_tbody input[type=checkbox]');
    var count = 0;
    checks.forEach(function(cb, i){
      if(!cb.disabled){ cb.checked = true; count++; }
    });
    updateSelectedCount();
    showToast('已全选 ' + count + ' 条可采集条目');
  };

  // ── Add To Task ──
  window.addToTask = function(){
    var checks = document.querySelectorAll('#candidate_tbody input[type=checkbox]');
    var selected = 0;
    checks.forEach(function(cb){ if(cb.checked && !cb.disabled) selected++; });

    var cmdBox = document.getElementById('task_cmd_box');
    cmdBox.style.display = 'block';
    cmdBox.innerHTML = '<strong>✅ ' + selected + ' 条候选来源已确认。</strong><br><br>' +
      '<strong>衔接采集命令：</strong><br>' +
      'D:/Python312/python.exe -m acs.scripts.run_shadow_batch --urls acs_data/discovery/selected_urls.txt --site-id discovery_task --max-urls 20 --rate-limit 0.3<br><br>' +
      '<span style="color:var(--text-dim)">ⓘ 该命令在安全测试模式下运行，仅写入 shadow 日志。</span>';

    showToast('已加入 ' + selected + ' 条候选来源到采集任务（仅 shadow 模式）');
  };

  // ── Update Selected Count ──
  function updateSelectedCount(){
    var checks = document.querySelectorAll('#candidate_tbody input[type=checkbox]');
    var total = 0, sel = 0;
    checks.forEach(function(cb){ total++; if(cb.checked) sel++; });
    var el = document.getElementById('sel_count');
    if(el) el.textContent = sel;
  }

  // ── Default dark mode ──
  document.body.classList.add('dark');

  // ── Monitor checkbox changes ──
  setInterval(function(){
    updateSelectedCount();
  }, 500);

})();
