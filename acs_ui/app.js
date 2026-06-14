/* ── ACS 资料采集助手 — App Logic ── */
(function(){
  'use strict';

  var API_BASE = 'http://127.0.0.1:5020';

  // ── Clock ──
  function updateClock(){
    var now = new Date(), s = now.toISOString().replace('T',' ').slice(0,19);
    var el = document.getElementById('clock'); if(el) el.textContent = s;
  }
  updateClock(); setInterval(updateClock, 1000);

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
    var body = document.body, icon = document.getElementById('theme-icon'), label = document.getElementById('theme-label');
    body.classList.toggle('dark');
    if(body.classList.contains('dark')){ icon.textContent = '☾'; label.textContent = '暗色'; }
    else { icon.textContent = '☀'; label.textContent = '亮色'; }
  };

  // ── Export Report ──
  window.exportReport = function(){
    var data = {
      version: 'ACS v1.0.0-sandbox', app: '资料采集助手',
      exported_at: new Date().toISOString(), total_entries: 86, success: 86, failed: 0,
      site: 'books.toscrape.com', completeness: '63.5%'
    };
    var blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = '资料导出_' + new Date().toISOString().slice(0,10) + '.json';
    a.click();
  };

  // ── Toast ──
  window.showToast = function(message) {
    var toast = document.getElementById('toast');
    if(!toast){ toast = document.createElement('div'); toast.id = 'toast'; toast.className = 'toast'; document.body.appendChild(toast); }
    toast.textContent = message; toast.classList.add('show');
    setTimeout(function(){ toast.classList.remove('show'); }, 2200);
  };

  // ── Provider Change ──
  window.onProviderChange = function(){
    var p = document.getElementById('provider_select').value;
    var descs = {'mock':'使用内置演示数据测试发现流程。','import-file':'从 CSV/JSON/TXT/Markdown 文件导入 URL 列表。','sitemap':'从公开 sitemap.xml 自动发现所有页面 URL。','rss':'从公开 RSS/Atom feed 提取文章链接。'};
    document.getElementById('provider_desc').textContent = descs[p] || '';
    ['mock','import','sitemap','rss'].forEach(function(k){
      var el = document.getElementById('inputs_'+k);
      if(el) el.style.display = (k === p) ? '' : 'none';
    });
  };

  // ── API call helper ──
  function apiCall(method, path, body, cb){
    var xhr = new XMLHttpRequest();
    xhr.open(method, API_BASE + path, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.timeout = 15000;
    xhr.onload = function(){
      try { var r = JSON.parse(xhr.responseText); cb(null, r, xhr.status); }
      catch(e){ cb(e, null, 0); }
    };
    xhr.onerror = function(){ cb(new Error('网络连接失败'), null, 0); };
    xhr.ontimeout = function(){ cb(new Error('请求超时'), null, 0); };
    xhr.send(body ? JSON.stringify(body) : null);
  }

  // ── Get provider input values ──
  function getProviderInput(){
    var p = document.getElementById('provider_select').value;
    var topic = '', keywords = '', pathOrUrl = '';
    if(p === 'mock'){
      topic = document.getElementById('topic_mock').value || '园区废气治理案例';
      keywords = document.getElementById('keywords_mock').value || 'VOCs,活性炭,整改报告';
    } else if(p === 'import-file'){
      pathOrUrl = document.getElementById('import_path').value;
      topic = document.getElementById('topic_import').value || '';
      keywords = document.getElementById('keywords_import').value || '';
    } else if(p === 'sitemap'){
      pathOrUrl = document.getElementById('sitemap_url').value;
      topic = document.getElementById('topic_sm').value || '';
      keywords = document.getElementById('keywords_sm').value || '';
    } else if(p === 'rss'){
      pathOrUrl = document.getElementById('feed_url').value;
      topic = document.getElementById('topic_rss').value || '';
      keywords = document.getElementById('keywords_rss').value || '';
    }
    return {provider: p, topic: topic, keywords: keywords, pathOrUrl: pathOrUrl};
  }

  // ── Run Discovery (API first, CLI fallback) ──
  var _lastResult = null;
  window.runDiscovery = function(){
    var inp = getProviderInput();
    var kws = inp.keywords.split(',').map(function(s){ return s.trim(); }).filter(function(s){ return s; });
    var body = { provider: inp.provider, topic: inp.topic, keywords: kws, limit: 20 };
    if(inp.provider === 'import-file') body.input_path = inp.pathOrUrl;
    if(inp.provider === 'sitemap') body.sitemap_url = inp.pathOrUrl;
    if(inp.provider === 'rss') body.feed_url = inp.pathOrUrl;

    showToast('正在发现候选来源...');

    apiCall('POST', '/api/discovery/run', body, function(err, result, status){
      if(err){
        // Fallback: show CLI command
        showCLIFallback(inp);
        return;
      }
      if(!result || result.error){
        showToast('错误: ' + (result ? result.error : '无响应'));
        showCLIFallback(inp);
        return;
      }
      _lastResult = result;
      renderCandidates(result);
      switchPage('candidates');
      showToast('发现 ' + result.total_candidates + ' 条候选来源');
    });
  };

  // ── CLI Fallback ──
  function showCLIFallback(inp){
    var cmd = 'D:/Python312/python.exe -m acs.discovery.discovery_cli --provider ' + inp.provider;
    if(inp.topic) cmd += ' --topic "' + inp.topic + '"';
    if(inp.keywords) cmd += ' --keywords "' + inp.keywords + '"';
    if(inp.provider === 'import-file') cmd += ' --input "' + inp.pathOrUrl + '"';
    if(inp.provider === 'sitemap') cmd += ' --sitemap-url "' + inp.pathOrUrl + '"';
    if(inp.provider === 'rss') cmd += ' --feed-url "' + inp.pathOrUrl + '"';
    cmd += ' --limit 20 --auto-select\n';
    cmd += 'D:/Python312/python.exe -m acs.scripts.run_shadow_batch --urls acs_data/discovery/selected_urls.txt --site-id discovery_task --max-urls 20 --rate-limit 0.3';

    var box = document.getElementById('discovery_cmd'); box.style.display = 'block';
    box.innerHTML = '<strong>⚠ 本地服务未启动。请在终端运行：</strong><br><br><code>' +
      'python -m acs.web.local_server --port 5020</code><br><br>' +
      '<strong>或直接运行发现命令：</strong><br><br><code>' +
      cmd.replace(/\n/g,'<br>').replace(/ /g,'&nbsp;') + '</code>';

    // Still show demo candidates
    _lastResult = null;
    document.getElementById('candidate_total').textContent = '6';
    document.getElementById('provider_label').textContent = '(演示数据)';
    switchPage('candidates');
  }

  // ── Render Candidates ──
  function renderCandidates(r){
    document.getElementById('candidate_total').textContent = r.total_candidates;
    document.getElementById('provider_label').textContent = '(' + r.query.provider + ')';
    document.getElementById('allowed_n').textContent = r.allowed_count;
    document.getElementById('review_n').textContent = r.needs_review_count;
    document.getElementById('blocked_n').textContent = r.blocked_count;

    var tbody = document.getElementById('candidate_tbody');
    tbody.innerHTML = '';
    (r.candidates || []).forEach(function(c){
      var isBlocked = c.compliance_status === 'blocked';
      var relCls = c.estimated_relevance >= 0.8 ? 'badge-green' : (c.estimated_relevance >= 0.6 ? 'badge-yellow' : 'badge-red');
      var statCls = isBlocked ? 'badge-red' : (c.compliance_status === 'needs_review' ? 'badge-yellow' : 'badge-green');
      var statTxt = isBlocked ? '禁止采集' : (c.compliance_status === 'needs_review' ? '需确认' : '可采集');
      var domain = c.source_domain || '';

      var tr = document.createElement('tr');
      if(isBlocked) tr.style.opacity = '0.45';
      tr.innerHTML =
        '<td>' + (isBlocked ? '<span style="color:var(--red)">✕</span>' : '<input type="checkbox" ' + (c.selected ? 'checked' : '') + (c.compliance_status === 'needs_review' ? '' : '') + '>') + '</td>' +
        '<td>' + escapeHtml(c.title || '(无标题)') + '</td>' +
        '<td style="font-family:monospace;font-size:11px">' + escapeHtml(domain + '/...') + '</td>' +
        '<td>' + escapeHtml(domain) + '</td>' +
        '<td><span class="' + relCls + '">' + Math.round(c.estimated_relevance * 100) + '%</span></td>' +
        '<td><span class="' + statCls + '">' + statTxt + '</span></td>' +
        '<td>' + (isBlocked ? '<span class="dim">' + escapeHtml(c.reason || '已拦截') + '</span>' : '<a href="#" class="link" onclick="showToast(\'URL: ' + escapeHtml(c.url || '') + '\')">预览</a>') + '</td>';
      tbody.appendChild(tr);
    });

    // Update selected count
    setTimeout(function(){
      var sel = 0, checks = document.querySelectorAll('#candidate_tbody input[type=checkbox]:checked');
      checks.forEach(function(){ sel++; });
      document.getElementById('sel_count').textContent = sel;
    }, 100);
  }

  function escapeHtml(s){ if(!s) return ''; return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // ── Select All Allowed ──
  window.selectAllAllowed = function(){
    var checks = document.querySelectorAll('#candidate_tbody input[type=checkbox]');
    var count = 0;
    checks.forEach(function(cb){ if(!cb.disabled){ cb.checked = true; count++; } });
    document.getElementById('sel_count').textContent = count;
    showToast('已全选 ' + count + ' 条可采集条目');
  };

  // ── Add To Task (API first) ──
  window.addToTask = function(){
    var checks = document.querySelectorAll('#candidate_tbody input[type=checkbox]');
    var urls = [], selected = 0;
    var rows = document.querySelectorAll('#candidate_tbody tr');
    rows.forEach(function(row, i){
      var cb = row.querySelector('input[type=checkbox]');
      if(cb && cb.checked){ selected++; }
    });
    // Collect URLs from _lastResult if available
    if(_lastResult && _lastResult.candidates){
      _lastResult.candidates.forEach(function(c, i){
        var row = rows[i]; if(!row) return;
        var cb = row.querySelector('input[type=checkbox]');
        if(cb && cb.checked) urls.push(c.url);
      });
    }

    if(selected === 0){ showToast('请至少选择一条候选来源'); return; }

    if(_lastResult && _lastResult.batch_id){
      apiCall('POST', '/api/discovery/select', { batch_id: _lastResult.batch_id, selected_urls: urls }, function(err, result, status){
        if(err || !result || result.error){
          showTaskCmd(selected);
          return;
        }
        apiCall('POST', '/api/tasks/create-from-selected', { batch_id: _lastResult.batch_id }, function(err2, r2){
          showTaskCmd(selected, r2);
        });
      });
    } else {
      showTaskCmd(selected);
    }
  };

  function showTaskCmd(selected, taskResult){
    var cmd = 'D:/Python312/python.exe -m acs.scripts.run_shadow_batch --urls acs_data/discovery/selected_urls.txt --site-id discovery_task --max-urls 20 --rate-limit 0.3';
    var box = document.getElementById('task_cmd_box'); box.style.display = 'block';
    var html = '<strong>✅ ' + selected + ' 条候选来源已确认。</strong><br><br>';
    if(taskResult){
      html += '<strong>任务 ID:</strong> ' + taskResult.task_id + '<br>';
      html += '<strong>采集命令:</strong><br><code>' + taskResult.command_preview + '</code><br><br>';
    } else {
      html += '<strong>采集命令:</strong><br><code>' + cmd + '</code><br><br>';
    }
    html += '<span style="color:var(--text-dim)">ⓘ 该命令在安全测试模式下运行，仅写入 shadow 日志。</span>';
    box.innerHTML = html;
    showToast('已加入 ' + selected + ' 条候选来源到采集任务（仅 shadow 模式）');

    // Show run button
    var runBtn = document.getElementById('run_shadow_btn');
    if(runBtn) runBtn.style.display = '';
  }

  // ── Run Shadow Task ──
  var _currentRunId = null, _pollTimer = null;
  window.runShadowTask = function(){
    var body = { task_id: 'discovery_task_' + Date.now(), max_urls: 20, rate_limit: 0.3 };
    showToast('正在启动安全测试采集...');

    apiCall('POST', '/api/tasks/run-shadow', body, function(err, result){
      if(err || !result || result.error){
        showToast('采集启动失败: ' + (result ? result.error : '服务未响应'));
        return;
      }
      _currentRunId = result.run_id;
      showToast('采集已启动: ' + result.run_id);

      // Start polling
      if(_pollTimer) clearInterval(_pollTimer);
      _pollTimer = setInterval(function(){ pollTaskStatus(_currentRunId); }, 2000);
      pollTaskStatus(_currentRunId);

      // Switch to results page
      switchPage('results');
    });
  };

  // ── Poll Task Status ──
  function pollTaskStatus(runId){
    if(!runId) return;
    apiCall('GET', '/api/tasks/status?run_id=' + runId, null, function(err, result){
      if(err || !result) return;
      renderTaskProgress(result);
      if(result.status === 'completed' || result.status === 'failed'){
        if(_pollTimer){ clearInterval(_pollTimer); _pollTimer = null; }
        loadResults(runId);
      }
    });
  }

  // ── Render Task Progress ──
  function renderTaskProgress(s){
    var statusEl = document.getElementById('task_status_text');
    var progEl = document.getElementById('task_progress_bar');
    var msgEl = document.getElementById('task_message');
    if(statusEl) statusEl.textContent = s.status || '';
    if(progEl){
      var pct = Math.round((s.progress || 0) * 100);
      progEl.style.width = pct + '%';
      progEl.textContent = pct + '%';
    }
    if(msgEl) msgEl.textContent = s.message || '';
    var okEl = document.getElementById('task_ok'), failEl = document.getElementById('task_fail');
    if(okEl) okEl.textContent = s.success || 0;
    if(failEl) failEl.textContent = s.failed || 0;
  }

  // ── Load Results ──
  function loadResults(runId){
    apiCall('GET', '/api/results/list?limit=100', null, function(err, result){
      if(err || !result){ showToast('加载结果失败'); return; }
      renderResultsTable(result.rows || []);
    });
  }

  // ── Render Results Table ──
  function renderResultsTable(rows){
    var tbody = document.getElementById('results_tbody');
    if(!tbody) return;
    tbody.innerHTML = '';
    rows.forEach(function(r, i){
      var tr = document.createElement('tr');
      var stCls = r.status === 'success' ? 'badge-green' : 'badge-red';
      var stTxt = r.status === 'success' ? '[PASS]' : '[FAIL]';
      tr.innerHTML =
        '<td>' + (i+1) + '</td>' +
        '<td style="font-family:monospace;font-size:11px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escapeHtml(r.url) + '">' + escapeHtml((r.url||'').substring(0,60)) + '</td>' +
        '<td>' + escapeHtml(r.title || '') + '</td>' +
        '<td>' + escapeHtml((r.description || '').substring(0,80)) + '</td>' +
        '<td>' + escapeHtml(r.price || '') + '</td>' +
        '<td><span class="' + stCls + '">' + stTxt + '</span></td>' +
        '<td>' + escapeHtml(r.failure_reason || '') + '</td>' +
        '<td>' + escapeHtml((r.collected_at || '').substring(0,16)) + '</td>';
      tbody.appendChild(tr);
    });
  }

  // ── Export Results ──
  window.exportResults = function(format){
    showToast('正在导出 ' + format.toUpperCase() + ' ...');
    apiCall('POST', '/api/results/export', {format: format}, function(err, result){
      if(err || !result || result.error){
        showToast('导出失败: ' + (result ? result.error : '服务未响应'));
        return;
      }
      showToast('已导出 ' + result.total + ' 条 → ' + result.path);
    });
  };

  // ── Check Service Status (poll on home page) ──
  function checkServiceStatus(){
    apiCall('GET', '/api/health', null, function(err, result){
      var icon = document.getElementById('svc_status_icon');
      var text = document.getElementById('svc_status_text');
      var mode = document.getElementById('svc_mode');
      if(err || !result || result.error){
        if(icon) icon.textContent = '[WARN]';
        if(text) text.textContent = '本地服务未连接 — 请运行 start_acs_desktop.bat 启动服务';
        if(mode) mode.textContent = '';
        return;
      }
      if(icon) icon.textContent = '[OK]';
      if(text) text.textContent = '本地服务已连接 — 可以开始智能找资料';
      if(mode) mode.textContent = '运行模式: ' + (result.acs_mode || 'shadow') + ' | 端口: 5020';
    });
  }

  // Check on load and every 30s
  checkServiceStatus();
  setInterval(checkServiceStatus, 30000);

  // ── Default dark mode ──
  document.body.classList.add('dark');

})();
