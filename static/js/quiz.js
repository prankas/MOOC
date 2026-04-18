(function () {
  var raw = sessionStorage.getItem("pq-quiz");
  if (!raw) {
    window.location.href = "/";
    return;
  }
  var pack = JSON.parse(raw);
  var sessionId = pack.session_id;
  var practice = !!pack.practice;
  var questions = pack.questions || [];
  var title = pack.title || "Quiz";
  var mode = pack.mode || "quick";

  var answers = {};

  function $(id) {
    return document.getElementById(id);
  }

  function themeBtn() {
    var t = document.documentElement.getAttribute("data-theme") || "dark";
    $("qz-theme").textContent = t === "dark" ? "☀" : "☾";
  }

  $("qz-theme").addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") || "dark";
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("pq-theme", next);
    themeBtn();
  });
  themeBtn();

  function modeLabel() {
    if (mode === "mock") return "Mock";
    if (mode === "week") return "Week-wise";
    return "Quick Quiz";
  }

  function refreshStatus() {
    var n = Object.keys(answers).length;
    var rem = questions.length - n;
    $("qz-status").textContent =
      (practice ? "Practice" : "Test") +
      " · " +
      modeLabel() +
      " · " +
      questions.length +
      " Questions · " +
      n +
      " answered · " +
      rem +
      " remaining";
  }

  function onPickPractice(qid, letter, card, btn) {
    if (card.dataset.done) return;
    fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        question_id: qid,
        answer: letter,
      }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        if (j.error) return;
        card.dataset.done = "1";
        answers[qid] = letter;
        card.querySelectorAll(".opt").forEach(function (o) {
          o.disabled = true;
          var L = o.dataset.letter;
          o.classList.remove("reveal-correct", "reveal-wrong");
          if (L === j.correct_letter) o.classList.add("reveal-correct");
        });
        if (!j.correct) btn.classList.add("reveal-wrong");
        refreshStatus();
      });
  }

  function onPickTest(qid, letter, card, btn) {
    card.querySelectorAll(".opt").forEach(function (o) {
      o.classList.remove("selected-opt");
    });
    btn.classList.add("selected-opt");
    answers[qid] = letter;
    refreshStatus();
  }

  function renderQuestions() {
    var host = $("qz-active");
    host.innerHTML = "";
    questions.forEach(function (q, idx) {
      var card = document.createElement("div");
      card.className = "q-card";
      var head = document.createElement("div");
      head.className = "q-head";
      head.textContent = "Q" + (idx + 1);
      var qt = document.createElement("p");
      qt.className = "q-text";
      qt.textContent = q.prompt;
      var opts = document.createElement("div");
      opts.className = "opts";
      ["A", "B", "C", "D"].forEach(function (L) {
        if (!q.options[L]) return;
        var b = document.createElement("button");
        b.type = "button";
        b.className = "opt";
        b.dataset.letter = L;
        var circ = document.createElement("span");
        circ.className = "letter";
        circ.textContent = L;
        var span = document.createElement("span");
        span.textContent = q.options[L];
        b.appendChild(circ);
        b.appendChild(span);
        b.addEventListener("click", function () {
          if (practice) onPickPractice(q.id, L, card, b);
          else onPickTest(q.id, L, card, b);
        });
        opts.appendChild(b);
      });
      card.appendChild(head);
      card.appendChild(qt);
      card.appendChild(opts);
      host.appendChild(card);
    });
  }

  function submitAll() {
    fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, answers: answers }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (res) {
        if (res.error) {
          alert(res.error);
          return;
        }
        $("qz-active").classList.add("hidden");
        $("qz-footer").classList.add("hidden");
        $("qz-results").classList.remove("hidden");
        $("rs-title").textContent = res.title || title;
        $("rs-score").textContent =
          "Score: " + res.correct + " / " + res.total + " correct";
        var det = $("rs-details");
        det.innerHTML = "";
        res.details.forEach(function (row, i) {
          var card = document.createElement("div");
          card.className = "q-card";
          var h = document.createElement("div");
          h.className = "q-head";
          h.textContent = "Q" + (i + 1) + (row.is_correct ? " ✓" : " ✗");
          var p = document.createElement("p");
          p.className = "q-text";
          p.textContent = row.prompt;
          var opts = document.createElement("div");
          opts.className = "opts";
          ["A", "B", "C", "D"].forEach(function (L) {
            if (!row.options[L]) return;
            var b = document.createElement("div");
            b.className = "opt";
            var circ = document.createElement("span");
            circ.className = "letter";
            circ.textContent = L;
            var span = document.createElement("span");
            span.textContent = row.options[L];
            b.appendChild(circ);
            b.appendChild(span);
            if (L === row.correct) b.classList.add("reveal-correct");
            if (row.user && L === row.user && L !== row.correct)
              b.classList.add("reveal-wrong");
            opts.appendChild(b);
          });
          card.appendChild(h);
          card.appendChild(p);
          card.appendChild(opts);
          det.appendChild(card);
        });
      });
  }

  $("qz-submit").addEventListener("click", submitAll);
  $("qz-reset").addEventListener("click", function () {
    sessionStorage.removeItem("pq-quiz");
    window.location.href = "/";
  });

  $("qz-title").textContent = title;
  renderQuestions();
  refreshStatus();

  /* optional: style for selected in test mode */
  var st = document.createElement("style");
  st.textContent =
    ".opt.selected-opt{border-color:var(--accent);background:var(--accent-dim)}";
  document.head.appendChild(st);
})();
