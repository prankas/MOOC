(function () {
  var BANK_ID = "default";
  var bankTitle = "Question bank";
  var total = 0;
  var weeks = [];
  var sources = [];
  var practice = localStorage.getItem("pq-practice") === "1";

  function $(id) {
    return document.getElementById(id);
  }

  function setMsg(el, text, err) {
    el.textContent = text || "";
    el.className = "msg" + (err ? " error" : "");
  }

  function themeBtnLabel() {
    var t = document.documentElement.getAttribute("data-theme") || "dark";
    $("btn-theme").textContent = t === "dark" ? "☀" : "☾";
  }

  function toggleTheme() {
    var cur = document.documentElement.getAttribute("data-theme") || "dark";
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("pq-theme", next);
    themeBtnLabel();
  }

  function togglePractice() {
    practice = !practice;
    localStorage.setItem("pq-practice", practice ? "1" : "0");
    $("btn-practice").style.opacity = practice ? "1" : "0.65";
  }

  function formatSources() {
    var el = $("bank-sources");
    if (!total) {
      el.textContent = "";
      return;
    }
    var parts = [total + " question" + (total === 1 ? "" : "s") + " in bank"];
    if (sources && sources.length) {
      parts.push("from: " + sources.join(", "));
    }
    el.textContent = parts.join(" · ");
  }

  function applyState(data) {
    if (!data) return;
    bankTitle = data.title || "Question bank";
    total = data.total || 0;
    weeks = data.weeks_available || [];
    sources = data.sources || [];
    updateDashboard();
    formatSources();
  }

  function fetchState() {
    return fetch("/api/state")
      .then(function (r) {
        return r.json();
      })
      .then(applyState)
      .catch(function () {});
  }

  function updateDashboard() {
    $("dash-title").textContent = bankTitle || "PDF Quiz";
    $("mock-meta").textContent =
      "All " + total + " questions · shuffled";
    $("mock-badge").textContent = total + " Q";
    document.querySelectorAll(".choice").forEach(function (c) {
      c.classList.remove("selected");
    });

    var wr = $("week-row");
    wr.innerHTML = "";
    if (!weeks.length) {
      var d = document.createElement("button");
      d.type = "button";
      d.className = "week-pill";
      d.disabled = true;
      d.textContent = "No week metadata";
      wr.appendChild(d);
      return;
    }
    weeks.forEach(function (w) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "week-pill";
      b.textContent = "Week " + w;
      b.addEventListener("click", function () {
        startQuiz("week", { week: w, count: 10 });
      });
      wr.appendChild(b);
    });
  }

  function startQuiz(mode, extra) {
    if (!total) {
      setMsg(
        $("upload-msg"),
        "Upload one or more PDFs first (or load the example).",
        true
      );
      return;
    }
    extra = extra || {};
    var body = { bank_id: BANK_ID, mode: mode };
    if (extra.count != null) body.count = extra.count;
    if (extra.week != null) body.week = extra.week;
    fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, j: j };
        });
      })
      .then(function (_ref) {
        var ok = _ref.ok;
        var j = _ref.j;
        if (!ok) throw new Error(j.error || "Start failed");
        var payload = {
          session_id: j.session_id,
          title: j.title,
          mode: mode,
          practice: practice,
          questions: j.questions,
          total: j.total,
        };
        sessionStorage.setItem("pq-quiz", JSON.stringify(payload));
        window.location.href = "/quiz";
      })
      .catch(function (e) {
        setMsg($("upload-msg"), e.message || String(e), true);
      });
  }

  function uploadFile(file) {
    if (!file) return;
    var fd = new FormData();
    fd.append("file", file);
    setMsg($("upload-msg"), "Uploading…");
    fetch("/api/upload", { method: "POST", body: fd })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, j: j };
        });
      })
      .then(function (_ref2) {
        var ok = _ref2.ok;
        var j = _ref2.j;
        if (!ok) throw new Error(j.error || "Upload failed");
        setMsg(
          $("upload-msg"),
          "Added " +
            (j.added || 0) +
            " from “" +
            (j.source || "PDF") +
            "”. Total in bank: " +
            (j.total || 0) +
            "."
        );
        return fetchState();
      })
      .catch(function (e) {
        setMsg($("upload-msg"), e.message || String(e), true);
      });
  }

  function loadExample() {
    setMsg($("upload-msg"), "Loading example…");
    fetch("/api/load-example", { method: "POST" })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, j: j };
        });
      })
      .then(function (_ref3) {
        var ok = _ref3.ok;
        var j = _ref3.j;
        if (!ok) throw new Error(j.error || "Could not load example");
        setMsg(
          $("upload-msg"),
          "Added " +
            (j.added || 0) +
            " from example. Total in bank: " +
            (j.total || 0) +
            "."
        );
        return fetchState();
      })
      .catch(function (e) {
        setMsg($("upload-msg"), e.message || String(e), true);
      });
  }

  function resetBank() {
    if (
      !confirm(
        "Clear the entire question bank? This removes all uploaded PDFs from this app until you add them again."
      )
    ) {
      return;
    }
    fetch("/api/reset", { method: "POST" })
      .then(function (r) {
        return r.json();
      })
      .then(function () {
        setMsg($("upload-msg"), "Question bank cleared.");
        return fetchState();
      })
      .catch(function () {
        setMsg($("upload-msg"), "Reset failed.", true);
      });
  }

  document.getElementById("btn-theme").addEventListener("click", toggleTheme);
  document.getElementById("btn-practice").addEventListener("click", togglePractice);
  $("btn-practice").style.opacity = practice ? "1" : "0.65";

  $("btn-reset-bank").addEventListener("click", resetBank);

  $("pdf-input").addEventListener("change", function () {
    var f = $("pdf-input").files && $("pdf-input").files[0];
    uploadFile(f);
    $("pdf-input").value = "";
  });

  $("btn-example").addEventListener("click", loadExample);

  $("card-mock").addEventListener("click", function () {
    startQuiz("mock", {});
  });
  $("card-mock").addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      startQuiz("mock", {});
    }
  });

  document.querySelectorAll("#quick-grid .choice").forEach(function (el) {
    el.addEventListener("click", function () {
      document.querySelectorAll("#quick-grid .choice").forEach(function (c) {
        c.classList.remove("selected");
      });
      el.classList.add("selected");
      var n = parseInt(el.getAttribute("data-n"), 10);
      startQuiz("quick", { count: n });
    });
  });

  themeBtnLabel();
  fetchState();
})();
