// Lakefront site: theme switch, mobile menu, table-of-contents highlight and dictionary search.
(function () {
  "use strict";
  var root = document.documentElement;

  // Light or dark. With no choice saved, the page follows the system setting.
  var toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var dark = root.dataset.theme
        ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
    });
  }

  // Menu on narrow screens.
  var menu = document.querySelector(".menu-toggle");
  var nav = document.getElementById("site-nav");
  if (menu && nav) {
    menu.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      menu.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // On narrow screens the dictionary's table list starts closed.
  var tablesNav = document.querySelector(".tables-nav-inner");
  if (tablesNav && window.matchMedia("(max-width: 1000px)").matches) tablesNav.open = false;

  // Highlight the section being read in "On this page".
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".toc a"));
  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[decodeURIComponent(a.hash.slice(1))] = a; });
    var headings = Object.keys(byId).map(function (id) { return document.getElementById(id); }).filter(Boolean);
    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
      var current = null;
      for (var i = 0; i < headings.length; i++) {
        if (headings[i].getBoundingClientRect().top < 140) current = headings[i].id;
      }
      tocLinks.forEach(function (a) { a.classList.remove("current"); });
      if (current && byId[current]) byId[current].classList.add("current");
    }, { rootMargin: "0px 0px -60% 0px" });
    headings.forEach(function (h) { observer.observe(h); });
  }

  // Territory map: switch between liability and comprehensive territories, and show a ZIP code on hover.
  Array.prototype.forEach.call(document.querySelectorAll(".terr-figure"), function (fig) {
    var svg = fig.querySelector(".terr-map");
    var tip = fig.querySelector(".map-tip");
    var wrap = fig.querySelector(".terr-map-wrap");
    var buttons = fig.querySelectorAll(".map-toggle button");
    Array.prototype.forEach.call(buttons, function (b) {
      b.addEventListener("click", function () {
        svg.dataset.view = b.dataset.view;
        Array.prototype.forEach.call(buttons, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        Array.prototype.forEach.call(fig.querySelectorAll(".map-note[data-for]"), function (n) {
          n.hidden = n.dataset.for !== b.dataset.view;
        });
      });
    });
    svg.addEventListener("mousemove", function (e) {
      var z = e.target.closest ? e.target.closest(".z") : null;
      if (!z) { tip.hidden = true; return; }
      if (z.nextSibling && z.nextSibling.classList && z.nextSibling.classList.contains("z")) z.parentNode.insertBefore(z, svg.querySelector(".county"));
      var liability = svg.dataset.view === "liability";
      tip.innerHTML = "<b>" + z.dataset.zip + "</b> <span>" + z.dataset.place + "</span><br>" +
        (liability ? "Liability territory <b>" + z.dataset.l + "</b><br><span>Comprehensive " + z.dataset.c + "</span>"
                   : "Comprehensive territory <b>" + z.dataset.c + "</b><br><span>Liability " + z.dataset.l + "</span>");
      var box = wrap.getBoundingClientRect();
      var x = e.clientX - box.left, y = e.clientY - box.top;
      tip.hidden = false;
      tip.style.left = Math.min(x + 14, box.width - tip.offsetWidth) + "px";
      tip.style.top = (y + 16) + "px";
    });
    svg.addEventListener("mouseleave", function () { tip.hidden = true; });
  });

  // Dictionary search: filters every column of every table as you type.
  var input = document.getElementById("dict-search");
  var data = document.getElementById("dict-index");
  if (input && data) {
    var index = JSON.parse(data.textContent);
    var results = document.getElementById("dict-results");
    var groups = document.getElementById("dict-groups");
    var overview = document.querySelector(".tables-nav a.all");
    var base = overview ? overview.getAttribute("href") : "./";

    var escape = function (s) {
      return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
    };
    var mark = function (text, terms) {
      var out = escape(text);
      terms.forEach(function (t) {
        if (!t) return;
        var re = new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
        out = out.replace(re, "<mark>$1</mark>");
      });
      return out;
    };

    var run = function () {
      var q = input.value.trim().toLowerCase();
      if (!q) { results.hidden = true; groups.hidden = false; return; }
      var terms = q.split(/\s+/);
      var hits = [];
      index.forEach(function (row) {
        var name = (row[0] + "." + row[1]).toLowerCase();
        var hay = name + " " + row[3].toLowerCase();
        if (!terms.every(function (t) { return hay.indexOf(t) !== -1; })) return;
        var score = 0;
        terms.forEach(function (t) {
          if (row[1].toLowerCase() === t || name === t) score += 10;
          else if (name.indexOf(t) !== -1) score += 4;
          else score += 1;
        });
        hits.push([score, row]);
      });
      hits.sort(function (a, b) { return b[0] - a[0]; });
      var html = '<p class="count">' + hits.length + (hits.length === 1 ? " column" : " columns") + "</p>";
      hits.slice(0, 200).forEach(function (h) {
        var r = h[1];
        html += '<a class="hit" href="' + base + r[0] + "/#" + r[1] + '">' +
          '<span class="hit-name"><span>' + mark(r[0], terms) + ".</span><b>" + mark(r[1], terms) + "</b></span>" +
          '<span class="hit-desc">' + mark(r[3], terms) + "</span></a>";
      });
      results.innerHTML = html;
      results.hidden = false;
      groups.hidden = true;
    };
    input.addEventListener("input", run);
    if (input.value) run();
  }
})();
