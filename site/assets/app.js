(function () {
  "use strict";

  // ---- Chamber graphic: seats in concentric arcs, coloured left to right.
  (function drawChamber() {
    var svg = document.getElementById("chamber-svg");
    if (!svg) return;
    var NS = "http://www.w3.org/2000/svg";
    var cx = 116, cy = 116;
    var rows = [{ r: 46, n: 13 }, { r: 62, n: 17 }, { r: 78, n: 21 }, { r: 94, n: 25 }, { r: 108, n: 29 }];
    rows.forEach(function (row) {
      for (var i = 0; i < row.n; i++) {
        var t = i / (row.n - 1);
        var a = Math.PI - t * Math.PI;
        var c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", (cx + row.r * Math.cos(a)).toFixed(1));
        c.setAttribute("cy", (cy - row.r * Math.sin(a)).toFixed(1));
        c.setAttribute("r", "3.6");
        var fill = t < 0.4 ? "var(--left)" : t > 0.6 ? "var(--right)" : "var(--seat-mid)";
        c.setAttribute("style", "fill:" + fill + ";opacity:" + (0.55 + 0.9 * Math.abs(t - 0.5)).toFixed(2));
        svg.appendChild(c);
      }
    });
    var podium = document.createElementNS(NS, "rect");
    podium.setAttribute("x", cx - 9); podium.setAttribute("y", cy - 8);
    podium.setAttribute("width", 18); podium.setAttribute("height", 8);
    podium.setAttribute("rx", 2);
    podium.setAttribute("style", "fill:var(--gold)");
    svg.appendChild(podium);
  })();

  var storiesEl = document.getElementById("stories");
  var picker = document.getElementById("edition-picker");
  var updatedEl = document.getElementById("updated");
  var toplineSection = document.getElementById("topline-section");
  var toplineEl = document.getElementById("topline");
  var oneSidedEl = document.getElementById("onesided");
  var feedStatusEl = document.getElementById("feedstatus");
  var dates = [];
  var cache = {};

  // ---- helpers
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function str(v) { return typeof v === "string" ? v : ""; }
  function safeUrl(u) { return typeof u === "string" && /^https:\/\//i.test(u) ? u : null; }
  function link(text, url, cls) {
    var href = safeUrl(url);
    if (!href) return el("span", cls, text);
    var a = el("a", cls, text);
    a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
    return a;
  }
  function fmtDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return iso || "";
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], 12));
    try {
      return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
    } catch (e) { return iso; }
  }
  function fmtTime(iso) {
    var d = new Date(iso || "");
    if (isNaN(d)) return "";
    try {
      return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid" }) + " Madrid";
    } catch (e) { return ""; }
  }
  function getJSON(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(path + " → " + r.status);
      return r.json();
    });
  }
  function showState(title, body) {
    storiesEl.textContent = "";
    var s = el("div", "state");
    s.appendChild(el("h2", null, title));
    s.appendChild(el("p", null, body));
    storiesEl.appendChild(s);
    toplineSection.hidden = true;
    oneSidedEl.hidden = true;
  }

  // ---- rendering
  function lens(side, data) {
    var box = el("div", "lens " + side);
    box.appendChild(el("div", "lens-title", side === "left" ? "From the left" : "From the right"));
    var angle = str(data && data.angle);
    if (angle) box.appendChild(el("p", "angle", angle));
    var outlets = data && Array.isArray(data.outlets) ? data.outlets : [];
    if (outlets.length) {
      var ul = el("ul", "outlets");
      outlets.forEach(function (o) {
        var li = el("li", "outlet");
        var headline = str(o.headline);
        li.appendChild(headline ? el("span", "outlet-name", str(o.name)) : link(str(o.name), o.url, "outlet-name"));
        li.appendChild(el("span", "outlet-lean", str(o.lean)));
        if (headline) li.appendChild(link(headline, o.url, "outlet-headline"));
        if (o.note) li.appendChild(el("span", "outlet-note", str(o.note)));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    } else if (!angle) {
      box.appendChild(el("p", "empty", "No coverage found from this side yet."));
    }
    return box;
  }

  function renderStory(s) {
    var art = el("article", "story");
    var head = el("div", "story-head");
    if (s.topic) head.appendChild(el("span", "topic", str(s.topic)));
    head.appendChild(el("h2", null, str(s.title)));
    art.appendChild(head);

    if (s.summary || s.why) {
      var facts = el("div", "facts");
      if (s.summary) {
        var what = el("div", "what");
        what.appendChild(el("span", "label", "What happened"));
        what.appendChild(el("p", null, str(s.summary)));
        facts.appendChild(what);
      }
      if (s.why) {
        var why = el("div", "why");
        why.appendChild(el("span", "label", "Why it matters for the EU"));
        why.appendChild(el("p", null, str(s.why)));
        facts.appendChild(why);
      }
      art.appendChild(facts);
    }

    var lenses = el("div", "lenses");
    lenses.appendChild(lens("left", s.left));
    lenses.appendChild(lens("right", s.right));
    art.appendChild(lenses);

    if (s.differ) {
      var d = el("div", "differ");
      d.appendChild(el("span", "differ-mark"));
      var dp = el("div");
      dp.appendChild(el("span", "label", "Where they differ"));
      dp.appendChild(el("p", null, str(s.differ)));
      d.appendChild(dp);
      art.appendChild(d);
    }

    var src = Array.isArray(s.sources) ? s.sources : [];
    if (src.length) {
      var p = el("p", "straight");
      p.appendChild(document.createTextNode("Straight reporting: "));
      src.forEach(function (o, i) {
        p.appendChild(link(str(o.name), o.url));
        if (i < src.length - 1) p.appendChild(document.createTextNode(" · "));
      });
      art.appendChild(p);
    }
    return art;
  }

  function renderOneSided(list, ul) {
    ul.textContent = "";
    if (!list.length) {
      ul.appendChild(el("li", "none", "Nothing stood out today."));
      return;
    }
    list.forEach(function (o) {
      var li = el("li");
      li.appendChild(link(str(o.title), o.url));
      li.appendChild(el("span", null, str(o.outlet) + (o.lean ? " · " + str(o.lean) : "")));
      ul.appendChild(li);
    });
  }

  function renderEdition(ed) {
    storiesEl.textContent = "";
    updatedEl.textContent = ed.generatedAt ? "Compiled " + fmtTime(ed.generatedAt) : "";
    toplineEl.textContent = str(ed.topline);
    toplineSection.hidden = !ed.topline;

    var stories = Array.isArray(ed.stories) ? ed.stories : [];
    if (stories.length) {
      stories.forEach(function (s) { storiesEl.appendChild(renderStory(s)); });
    } else {
      var s = el("div", "state");
      s.appendChild(el("h2", null, "No shared stories in this edition"));
      s.appendChild(el("p", null, "Neither side covered the same EU story in the feeds that morning. See what each side covered on its own below."));
      storiesEl.appendChild(s);
    }

    var os = ed.oneSided || {};
    var left = Array.isArray(os.left) ? os.left : [];
    var right = Array.isArray(os.right) ? os.right : [];
    oneSidedEl.hidden = !left.length && !right.length;
    renderOneSided(left, document.getElementById("only-left"));
    renderOneSided(right, document.getElementById("only-right"));

    var bits = [];
    if (ed.feeds && ed.feeds.total) {
      bits.push(ed.feeds.ok + " of " + ed.feeds.total + " feeds read");
      if (ed.feeds.failed && ed.feeds.failed.length) bits.push("unreachable: " + ed.feeds.failed.join(", "));
    }
    if (ed.mode === "headlines") bits.push("headlines mode (add an API key for written summaries)");
    feedStatusEl.textContent = bits.length ? "This edition: " + bits.join(" · ") : "";
  }

  function renderShelf(shelf) {
    var root = document.getElementById("shelf");
    root.textContent = "";
    [["left", "Left-leaning"], ["centre", "Straight news"], ["right", "Right-leaning"]].forEach(function (pair) {
      var col = el("div", "s-" + pair[0]);
      col.appendChild(el("h3", null, pair[1]));
      var ul = el("ul");
      (shelf[pair[0]] || []).forEach(function (o) {
        var li = el("li", null, str(o.name));
        var meta = [str(o.lean), str(o.country)].filter(Boolean).join(" · ");
        if (meta) li.appendChild(el("span", null, meta));
        ul.appendChild(li);
      });
      col.appendChild(ul);
      root.appendChild(col);
    });
  }

  // ---- editions + routing (#2026-10-27 opens that day's edition)
  function wanted() {
    var h = (location.hash || "").replace(/^#/, "");
    return dates.indexOf(h) >= 0 ? h : dates[0];
  }

  function show(date) {
    Array.prototype.forEach.call(picker.options, function (o) { o.selected = o.value === date; });
    if (cache[date]) { renderEdition(cache[date]); return; }
    getJSON("data/editions/" + date + ".json").then(function (ed) {
      cache[date] = ed;
      if (wanted() === date) renderEdition(ed);
    }).catch(function () {
      showState("That edition couldn't load", "Try another date from the Edition menu, or reload the page.");
    });
  }

  picker.addEventListener("change", function () {
    var v = picker.value;
    if (v === dates[0]) {
      history.replaceState(null, "", location.pathname + location.search);
      show(v);
    } else {
      location.hash = v;
    }
  });
  window.addEventListener("hashchange", function () { if (dates.length) show(wanted()); });

  getJSON("data/outlets.json").then(renderShelf).catch(function () {});

  getJSON("data/index.json").then(function (idx) {
    dates = (idx && Array.isArray(idx.editions) ? idx.editions : []).filter(function (d) { return /^\d{4}-\d{2}-\d{2}$/.test(d); });
    if (!dates.length) {
      picker.textContent = "";
      picker.appendChild(el("option", null, "No editions yet"));
      showState("No edition yet", "The first brief appears here after the bot's first morning run.");
      return;
    }
    picker.textContent = "";
    dates.forEach(function (d, i) {
      var o = el("option", null, fmtDate(d) + (i === 0 ? " · latest" : ""));
      o.value = d;
      picker.appendChild(o);
    });
    picker.disabled = false;
    show(wanted());
  }).catch(function () {
    picker.textContent = "";
    picker.appendChild(el("option", null, "Unavailable"));
    showState("Editions couldn't load", "If you opened index.html straight from your computer, start a local preview instead (see the README). Online, reload the page.");
  });
})();
