// ===== Scroll reveal =====
(function () {
  var items = document.querySelectorAll('.reveal');
  if (!items.length) return;
  if (!('IntersectionObserver' in window)) {
    items.forEach(function (el) { el.classList.add('is-visible'); });
    return;
  }
  // threshold 0 (rather than a fraction of the target's own height) so very
  // tall blocks - e.g. the 14-question final quiz - reveal as soon as they
  // start entering the viewport, instead of requiring an unreachable amount
  // of their own height to be on-screen at once.
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0 });
  items.forEach(function (el) {
    var r = el.getBoundingClientRect();
    // Not every browser reliably fires an initial IntersectionObserver
    // callback for a target that already overlaps the viewport at the
    // moment observe() is called - reveal those immediately instead of
    // waiting on an observer notification that may never come.
    if (r.top < window.innerHeight && r.bottom > 0) {
      el.classList.add('is-visible');
    } else {
      io.observe(el);
    }
  });
  // Safety net: reveal-on-scroll should never leave real content stuck at
  // opacity 0 (e.g. if a stylesheet was still loading when this ran and
  // layout measurements above were briefly inaccurate). Anything not
  // already revealed gets shown after a short delay no matter what.
  setTimeout(function () {
    document.querySelectorAll('.reveal:not(.is-visible)').forEach(function (el) {
      el.classList.add('is-visible');
    });
  }, 1500);
})();

// ===== Stat bars (home page comparison, if present) =====
(function () {
  var rows = document.querySelectorAll('.stat-row');
  if (!rows.length || !('IntersectionObserver' in window)) {
    rows.forEach(function (r) { r.classList.add('is-visible'); });
    return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add('is-visible');
        io.unobserve(entry.target);
      }
    });
  }, { threshold: 0.3 });
  rows.forEach(function (r) { io.observe(r); });
})();

// ===== Tabs (source/translation pages) =====
(function () {
  var tabGroups = document.querySelectorAll('.tabs');
  tabGroups.forEach(function (group) {
    var btns = group.querySelectorAll('.tab-btn');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var targetId = btn.getAttribute('data-tab');
        var panelWrap = group.parentElement;
        btns.forEach(function (b) { b.setAttribute('aria-selected', 'false'); });
        btn.setAttribute('aria-selected', 'true');
        panelWrap.querySelectorAll(':scope > .tab-panel').forEach(function (p) {
          p.hidden = (p.id !== targetId);
        });
      });
    });
  });
})();

// ===== Mobile menu toggle =====
// One hamburger button serves two different jobs depending on the page:
// - Chapter pages (which have a .side-nav): opens the sidebar drawer.
// - Every other page: opens a dropdown with the top nav links, since the
//   top <ul> is hidden below 640px and would otherwise leave no navigation.
(function () {
  var toggle = document.querySelector('.menu-toggle');
  if (!toggle) return;
  var sideNav = document.querySelector('.side-nav');

  if (sideNav) {
    var backdrop = document.createElement('div');
    backdrop.className = 'side-nav-backdrop';
    document.body.appendChild(backdrop);

    function close() {
      document.body.classList.remove('nav-open');
      sideNav.classList.remove('is-open');
    }
    toggle.addEventListener('click', function () {
      document.body.classList.toggle('nav-open');
      sideNav.classList.toggle('is-open');
    });
    backdrop.addEventListener('click', close);
    sideNav.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', close);
    });
  } else {
    var nav = document.querySelector('.site-nav');
    if (!nav) return;
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('menu-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.querySelectorAll('a.nav-link').forEach(function (a) {
      a.addEventListener('click', function () { nav.classList.remove('menu-open'); });
    });
  }
})();

// ===== Global site search =====
(function () {
  var toggle = document.querySelector('.search-toggle');
  var panel = document.querySelector('.site-search');
  var input = document.querySelector('#site-search-input');
  var resultsEl = document.querySelector('.site-search-results');
  if (!toggle || !panel || !input || !resultsEl) return;

  var basePath = document.body.getAttribute('data-rel') || '';
  var indexData = null;

  function ensureIndex() {
    if (indexData) return Promise.resolve(indexData);
    return fetch(basePath + 'assets/search-index.json')
      .then(function (r) { return r.json(); })
      .then(function (data) { indexData = data; return data; })
      .catch(function () { indexData = []; return []; });
  }

  function openPanel() {
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    ensureIndex().then(function () { input.focus(); });
  }
  function closePanel() {
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    resultsEl.hidden = true;
    resultsEl.innerHTML = '';
    input.value = '';
  }
  toggle.addEventListener('click', function () {
    if (panel.hidden) openPanel(); else closePanel();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closePanel();
  });
  document.addEventListener('click', function (e) {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== toggle) closePanel();
  });

  input.addEventListener('input', function () {
    var q = input.value.trim();
    if (q.length < 2) { resultsEl.hidden = true; resultsEl.innerHTML = ''; return; }
    ensureIndex().then(function (data) {
      var ql = q.toLowerCase();
      var matches = data.filter(function (item) {
        return item.title.toLowerCase().indexOf(ql) !== -1;
      }).slice(0, 8);
      if (!matches.length) {
        resultsEl.innerHTML = '<p class="search-empty">אין תוצאות עבור “' + q + '”.</p>';
      } else {
        resultsEl.innerHTML = matches.map(function (item) {
          var tag = item.type === 'glossary' ? 'מילון' : (item.type === 'research' ? 'מחקר · פרק ' + item.chapter : 'פרק ' + item.chapter);
          return '<a href="' + basePath + item.url + '"><span class="sr-title">' + item.title + '</span><span class="sr-tag">' + tag + '</span></a>';
        }).join('');
      }
      resultsEl.hidden = false;
    });
  });
})();

// ===== Reading progress tracker (localStorage) =====
(function () {
  var KEY = 'synthwave-progress';
  function getProgress() {
    try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; }
  }
  function setProgress(p) {
    try { localStorage.setItem(KEY, JSON.stringify(p)); } catch (e) {}
  }
  function countDone(p) {
    return Object.keys(p).filter(function (k) { return p[k]; }).length;
  }

  var progress = getProgress();
  document.querySelectorAll('.side-nav a.ch-link[data-ch]').forEach(function (a) {
    if (progress[a.getAttribute('data-ch')]) a.classList.add('is-complete');
  });

  var btn = document.querySelector('.complete-btn');
  if (btn) {
    var num = btn.getAttribute('data-ch');
    var textEl = btn.querySelector('.complete-text');
    function refreshBtn() {
      var done = !!getProgress()[num];
      btn.classList.toggle('is-done', done);
      if (textEl) textEl.textContent = done ? 'הפרק סומן כהושלם — לחצו לביטול' : 'סמן פרק זה כהושלם';
    }
    refreshBtn();
    btn.addEventListener('click', function () {
      var p = getProgress();
      p[num] = !p[num];
      setProgress(p);
      refreshBtn();
      var sideLink = document.querySelector('.side-nav a.ch-link[data-ch="' + num + '"]');
      if (sideLink) sideLink.classList.toggle('is-complete', !!p[num]);
    });
  }

  var fill = document.getElementById('progress-fill');
  var count = document.getElementById('progress-count');
  if (fill && count) {
    var done = countDone(getProgress());
    var pct = Math.round((done / 8) * 100);
    fill.style.width = pct + '%';
    count.textContent = done + ' מתוך 8 פרקים הושלמו';
  }
})();

// ===== Sidebar: mark current page/section as active =====
(function () {
  var links = document.querySelectorAll('.side-nav a');
  if (!links.length) return;
  var here = window.location.pathname.split('/').pop() || 'index.html';
  links.forEach(function (a) {
    var href = a.getAttribute('href') || '';
    var hrefFile = href.split('#')[0].split('/').pop();
    if (hrefFile === here && !href.includes('#')) {
      a.classList.add('current');
    }
  });
})();

// ===== Glossary live search =====
(function () {
  var input = document.querySelector('#glossary-search');
  if (!input) return;
  var items = document.querySelectorAll('.term-item');
  var letters = document.querySelectorAll('.term-letter');
  input.addEventListener('input', function () {
    var q = input.value.trim().toLowerCase();
    items.forEach(function (item) {
      var text = item.textContent.toLowerCase();
      item.hidden = q.length > 0 && text.indexOf(q) === -1;
    });
    letters.forEach(function (letter) {
      var next = letter.nextElementSibling;
      var anyVisible = false;
      while (next && !next.classList.contains('term-letter')) {
        if (!next.hidden) { anyVisible = true; break; }
        next = next.nextElementSibling;
      }
      letter.hidden = q.length > 0 && !anyVisible;
    });
  });
})();

// ===== Self-check quizzes =====
(function () {
  document.querySelectorAll('.quiz-card').forEach(function (card) {
    var checkBtn = card.querySelector('.quiz-check');
    var feedback = card.querySelector('.quiz-feedback');
    if (!checkBtn) return;
    checkBtn.addEventListener('click', function () {
      var opts = card.querySelectorAll('.quiz-opt');
      var checked = card.querySelector('input[type="radio"]:checked');
      if (!checked) {
        feedback.textContent = 'נא לבחור תשובה לפני הבדיקה.';
        feedback.className = 'quiz-feedback show bad';
        return;
      }
      var isCorrect = checked.getAttribute('data-correct') === 'true';
      opts.forEach(function (opt) {
        var input = opt.querySelector('input');
        if (input.getAttribute('data-correct') === 'true') opt.classList.add('correct');
        else if (input.checked) opt.classList.add('incorrect');
        input.disabled = true;
      });
      feedback.textContent = isCorrect
        ? '✔ נכון. ' + (checked.getAttribute('data-explain') || '')
        : '✘ לא מדויק. ' + (checked.getAttribute('data-explain') || '');
      feedback.className = 'quiz-feedback show ' + (isCorrect ? 'ok' : 'bad');
      checkBtn.disabled = true;
      checkBtn.style.opacity = '.5';
      card.dataset.result = isCorrect ? 'correct' : 'incorrect';

      // update running "answered" count for this quiz block if present
      var block = card.closest('.quiz-block');
      if (block) {
        var total = block.querySelectorAll('.quiz-card').length;
        var answered = block.querySelectorAll('.quiz-check:disabled').length;
        var scoreEl = block.querySelector('.quiz-score');
        if (block.classList.contains('final-quiz')) {
          var correct = block.querySelectorAll('.quiz-card[data-result="correct"]').length;
          if (scoreEl) {
            scoreEl.textContent = 'ענית על ' + answered + ' מתוך ' + total + ' שאלות · ' + correct + ' נכונות עד כה.';
          }
          if (answered === total) {
            var pct = Math.round((correct / total) * 100);
            var resultEl = block.querySelector('.final-quiz-result');
            if (resultEl) {
              resultEl.hidden = false;
              var pctEl = resultEl.querySelector('.final-quiz-pct');
              var detailEl = resultEl.querySelector('.final-quiz-detail');
              if (pctEl) pctEl.textContent = pct + '%';
              if (detailEl) detailEl.textContent = correct + ' תשובות נכונות מתוך ' + total + '.';
              resultEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            try {
              localStorage.setItem('synthwave-finalquiz-score', JSON.stringify({
                percent: pct, correct: correct, total: total, date: new Date().toISOString()
              }));
            } catch (e) {}
          }
        } else if (scoreEl) {
          scoreEl.textContent = 'ענית על ' + answered + ' מתוך ' + total + ' שאלות.';
        }
      }
    });
  });
})();

// ===== Final quiz: show previously-saved score, if any =====
(function () {
  var el = document.getElementById('final-quiz-previous');
  if (!el) return;
  try {
    var s = JSON.parse(localStorage.getItem('synthwave-finalquiz-score'));
    if (s && typeof s.percent === 'number') {
      var pctEl = el.querySelector('.prev-pct');
      var dateEl = el.querySelector('.prev-date');
      if (pctEl) pctEl.textContent = s.percent + '%';
      if (dateEl) {
        var d = new Date(s.date);
        dateEl.textContent = isNaN(d.getTime()) ? '' : d.toLocaleDateString('he-IL');
      }
      el.hidden = false;
    }
  } catch (e) {}
})();
