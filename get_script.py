SCRIPT_CONTENT = """// ==UserScript==
// @name         KickBot Master Suite UI
// @namespace    http://tampermonkey.net/
// @version      5.5
// @description  KickBot Floating Console UI & Auto Watcher
// @match        https://kick.com/*
// @grant        GM_openInTab
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==UserScript==

(function () {
    'use strict';

    var DASHBOARD_API = "https://kickbot-tracker.online/api/v1/live-data";
    var WATCH_ROTATION_LIMIT_MS = 3600000;
    var DROP_BLACKLIST_COOLDOWN_MS = 600000;

    var currentUrl = window.location.href;
    var currentPath = window.location.pathname.replace(/^\/+/, '').toLowerCase();

    if (currentUrl.indexOf("/drops/inventory") !== -1) {
        setInterval(function () {
            GM_setValue("inventory_tab_ping", Date.now());
            var buttons = document.querySelectorAll('button');
            buttons.forEach(function (btn) {
                var text = (btn.textContent || '').trim().toLowerCase();
                var aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                if (aria.indexOf('daily reward') !== -1 || aria.indexOf('hadiah harian') !== -1) return;
                var isClaim = text === 'klaim' || text === 'claim' || aria.indexOf('klaim') !== -1 || (aria.indexOf('claim') !== -1 && aria.indexOf('daily') === -1);
                var isClaimed = text.indexOf('claimed') !== -1 || text.indexOf('diklaim') !== -1 || btn.disabled || btn.offsetParent === null;
                if (isClaim && !isClaimed) btn.click();
            });
        }, 6000);
        setTimeout(function () { location.reload(); }, 900000);
        return;
    }

    if (currentUrl.indexOf("action=autofollow") !== -1) {
        var attempts = 0;
        var interval = setInterval(function () {
            attempts++;
            var already = document.querySelector('button[aria-label="Following"], button[aria-label="Unfollow"]') ||
                Array.from(document.querySelectorAll('button')).some(function(btn) { return (btn.textContent || '').toLowerCase().indexOf('following') !== -1; });
            if (already) { finishFollow(true); clearInterval(interval); return; }
            var followBtn = document.querySelector('button[data-testid="follow-button"]') || document.querySelector('button[aria-label="Follow"]');
            if (followBtn) { followBtn.click(); setTimeout(function () { finishFollow(true); clearInterval(interval); }, 1500); return; }
            if (attempts >= 15) { finishFollow(false); clearInterval(interval); }
        }, 800);
        function finishFollow(success) {
            GM_setValue("last_follow_status", { streamer: currentPath, success: success, time: Date.now() });
            setTimeout(function () { window.close(); }, 800);
        }
        return;
    }

    function createFloatingUI() {
        if (document.getElementById('kick-bot-floating-ui')) return;
        var ui = document.createElement('div');
        ui.id = 'kick-bot-floating-ui';
        var htmlStr = '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">' +
            '<div style="display:flex; align-items:center; gap:8px;">' +
            '<div style="background:#53fc18; color:#000; font-weight:900; width:26px; height:26px; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:16px;">K</div>' +
            '<div><div style="font-weight:bold; color:#53fc18; font-size:13px; line-height:1.1;">KICK DROPS BOT <span style="color:#a855f7;">v1.6</span></div>' +
            '<div style="font-size:10px; color:#94a3b8;">Status: <span style="color:#53fc18;">● System Ready</span></div></div></div>' +
            '<button id="kb-btn-minimize" style="background:#334155; color:#fff; border:none; border-radius:4px; width:22px; height:22px; cursor:pointer; font-weight:bold;">-</button></div>' +
            '<div id="kb-ui-body"><div style="background:#0284c7; color:#fff; font-size:11px; font-weight:bold; text-align:center; padding:6px; border-radius:4px; margin-bottom:8px;">🌐 Global Mode (Auto-Sniper Ready)</div>' +
            '<div style="display:flex; gap:6px; margin-bottom:8px;"><input type="text" id="kb-input-streamer" placeholder="Isi nama streamer (cth: st1, st2)" style="flex:1; background:#1e293b; border:1px solid #334155; color:#fff; border-radius:4px; padding:6px 8px; font-size:11px;">' +
            '<button id="kb-btn-play" style="background:#22c55e; color:#000; font-weight:bold; border:none; border-radius:4px; padding:0 12px; cursor:pointer; font-size:11px;">▶ Play</button></div>' +
            '<div style="display:flex; gap:6px; margin-bottom:8px;"><select id="kb-select-streamer" style="flex:1; background:#1e293b; border:1px solid #334155; color:#fff; border-radius:4px; padding:6px; font-size:11px;"><option value="">Pilih (Memuat Live...)</option></select>' +
            '<button id="kb-btn-refresh" style="background:#0284c7; color:#fff; border:none; border-radius:4px; padding:0 8px; cursor:pointer;">🔄</button>' +
            '<button id="kb-btn-p1" style="background:#eab308; color:#000; font-weight:bold; border:none; border-radius:4px; padding:0 8px; cursor:pointer; font-size:11px;">▶ 1</button>' +
            '<button id="kb-btn-p4" style="background:#ec4899; color:#fff; font-weight:bold; border:none; border-radius:4px; padding:0 8px; cursor:pointer; font-size:11px;">▶ 4</button></div>' +
            '<div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:6px; border-radius:4px; margin-bottom:8px; border:1px solid #1e293b;">' +
            '<span id="kb-active-streamer-name" style="font-weight:bold; color:#22c55e; font-size:12px;">-</span>' +
            '<div style="display:flex; align-items:center; gap:6px;"><span id="kb-watch-timer" style="background:#1e293b; border:1px solid #334155; color:#fff; font-family:monospace; padding:2px 6px; border-radius:4px; font-size:11px;">00:00</span>' +
            '<button id="kb-btn-follow-active" style="background:#2563eb; color:#fff; border:none; border-radius:4px; padding:3px 8px; font-size:10px; font-weight:bold; cursor:pointer;">Follow</button>' +
            '<button id="kb-btn-close-active" style="background:#ef4444; color:#fff; border:none; border-radius:4px; padding:3px 8px; font-size:10px; font-weight:bold; cursor:pointer;">X</button></div></div>' +
            '<div id="kb-video-container" style="position:relative; width:100%; height:160px; background:#000; border-radius:6px; overflow:hidden; margin-bottom:8px; border:1px solid #334155;"><iframe id="kb-video-iframe" src="" style="width:100%; height:100%; border:none;" allowfullscreen></iframe></div>' +
            '<div id="kb-log-box" style="height:60px; overflow-y:auto; background:#020617; border:1px solid #1e293b; border-radius:4px; padding:5px; font-family:monospace; font-size:10px; color:#22c55e; margin-bottom:8px;"><div>🚀 Bot v1.6 Aktif!..</div></div>' +
            '<div style="display:flex; flex-direction:column; gap:6px; margin-bottom:8px;"><button id="kb-btn-sniper" style="background:#a855f7; color:#fff; font-weight:bold; border:none; border-radius:6px; padding:8px; cursor:pointer; font-size:11px; display:flex; align-items:center; justify-content:center; gap:6px;">🎯 AKTIFKAN AUTO-SNIPER DROPS</button>' +
            '<div style="display:flex; gap:6px;"><button id="kb-btn-toggle-video" style="flex:1; background:#0284c7; color:#fff; font-weight:bold; border:none; border-radius:6px; padding:8px; cursor:pointer; font-size:10px;">👁️ SEMBUNYIKAN VIDEO</button>' +
            '<button id="kb-btn-claim-manual" style="flex:1; background:#15803d; color:#fff; font-weight:bold; border:none; border-radius:6px; padding:8px; cursor:pointer; font-size:10px;">CLAIM MANUAL</button></div></div>' +
            '<div style="text-align:center; font-size:9px; color:#e2e8f0; font-weight:bold;">⚡ Auto-Claim (6s) | Sniper Drop(60s)</div></div>';
        ui.innerHTML = htmlStr;
        Object.assign(ui.style, { position: 'fixed', top: '20px', right: '20px', width: '320px', backgroundColor: '#090d16', border: '1.5px solid #22c55e', borderRadius: '10px', padding: '10px', boxShadow: '0 8px 24px rgba(0,0,0,0.8)', zIndex: '999999', fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif" });
        document.body.appendChild(ui);
        document.getElementById('kb-btn-minimize').addEventListener('click', function () { var body = document.getElementById('kb-ui-body'); body.style.display = body.style.display === 'none' ? 'block' : 'none'; });
        document.getElementById('kb-btn-toggle-video').addEventListener('click', function () { var vContainer = document.getElementById('kb-video-container'); var btn = document.getElementById('kb-btn-toggle-video'); if (vContainer.style.display === 'none') { vContainer.style.display = 'block'; btn.innerText = '👁️ SEMBUNYIKAN VIDEO'; } else { vContainer.style.display = 'none'; btn.innerText = '👁️ TAMPILKAN VIDEO'; } });
        document.getElementById('kb-btn-play').addEventListener('click', function () { var val = document.getElementById('kb-input-streamer').value.trim().toLowerCase(); if (val) switchStreamer(val); });
        document.getElementById('kb-select-streamer').addEventListener('change', function (e) { if (e.target.value) switchStreamer(e.target.value); });
        document.getElementById('kb-btn-refresh').addEventListener('click', populateDropdownList);
    }

    function addLog(msg) { var logBox = document.getElementById('kb-log-box'); if (logBox) { var time = new Date().toLocaleTimeString(); var div = document.createElement('div'); div.innerText = time + ' ' + msg; logBox.appendChild(div); logBox.scrollTop = logBox.scrollHeight; } }
    function populateDropdownList() { fetch(DASHBOARD_API).then(function(res) { return res.json(); }).then(function(data) { if (data.status === "success") { var select = document.getElementById('kb-select-streamer'); if (!select) return; select.innerHTML = '<option value="">Pilih (' + data.rankings.length + ' Live)</option>'; data.rankings.forEach(function(s) { var opt = document.createElement('option'); opt.value = s.channel.toLowerCase(); opt.innerText = s.channel + ' (' + s.viewers + ')'; select.appendChild(opt); }); } }).catch(function(e) {}); }

    var watchTimerInterval = null; var watchSeconds = 0;
    function switchStreamer(streamer) { addLog('📺 Memuat stream ' + streamer + '...'); var activeEl = document.getElementById('kb-active-streamer-name'); if (activeEl) activeEl.innerText = streamer; var iframe = document.getElementById('kb-video-iframe'); if (iframe) iframe.src = 'https://player.kick.com/' + streamer; if (watchTimerInterval) clearInterval(watchTimerInterval); watchSeconds = 0; watchTimerInterval = setInterval(function () { watchSeconds++; var mins = String(Math.floor(watchSeconds / 60)).padStart(2, '0'); var secs = String(watchSeconds % 60).padStart(2, '0'); var timerEl = document.getElementById('kb-watch-timer'); if (timerEl) timerEl.innerText = mins + ':' + secs; }, 1000); }

    function startMasterWatchLoop() {
        createFloatingUI(); populateDropdownList();
        var lastPing = GM_getValue("inventory_tab_ping", 0);
        if (Date.now() - lastPing > 35000) { GM_openInTab("https://kick.com/drops/inventory", { active: false, background: true }); }
        fetch(DASHBOARD_API).then(function(res) { return res.json(); }).then(function(data) {
            if (data.status !== "success") return;
            var liveRankings = data.rankings || []; var topDrops = data.top_drops || []; var liveChannelsSet = new Set(liveRankings.map(function(s) { return s.channel.toLowerCase(); }));
            var dropBlacklist = GM_getValue("drop_blacklist", {}); var watchedHistory = GM_getValue("watched_history", {}); var now = Date.now();
            for (var ch in dropBlacklist) { if (now - dropBlacklist[ch] > DROP_BLACKLIST_COOLDOWN_MS) delete dropBlacklist[ch]; }
            GM_setValue("drop_blacklist", dropBlacklist);
            var targetStreamer = null;
            for (var i = 0; i < topDrops.length; i++) { var username = topDrops[i].streamer.toLowerCase(); if (liveChannelsSet.has(username) && !dropBlacklist[username]) { var lastWatched = watchedHistory[username] || 0; if (now - lastWatched > WATCH_ROTATION_LIMIT_MS) { targetStreamer = username; break; } } }
            if (!targetStreamer) { for (var j = 0; j < liveRankings.length; j++) { var u = liveRankings[j].channel.toLowerCase(); if (!dropBlacklist[u]) { var lw = watchedHistory[u] || 0; if (now - lw > WATCH_ROTATION_LIMIT_MS) { targetStreamer = u; break; } } } }
            if (!targetStreamer && liveRankings.length > 0) { targetStreamer = liveRankings[0].channel.toLowerCase(); }
            if (targetStreamer) switchStreamer(targetStreamer);
        }).catch(function(e) {});
    }
    setTimeout(startMasterWatchLoop, 2500);
})();"""
