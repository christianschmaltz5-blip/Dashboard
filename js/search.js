/* ARC Search — floating AI assistant widget, injected on every page */
(function () {

  // Detect if we're in the pages/ subdirectory
  const inPages = window.location.pathname.includes('/pages/');
  const toPages = inPages ? '' : 'pages/';
  const toRoot  = inPages ? '../' : '';

  // ── KNOWLEDGE BASE ────────────────────────────────────────────────────
  const KB = [
    {
      title: "Market Report Agent",
      file: "pages/market-report.html",
      tags: ["mls", "market", "report", "zillow", "fred", "mortgage", "rates", "closed", "pending", "sold", "listings", "weekly", "monday", "email", "black hills", "rapid city", "spearfish", "sturgis", "hot springs", "box elder", "home value", "zhvi", "inventory", "sale price"],
      summary: "Weekly market update every Monday 6 AM — mortgage rates, home values, and sales activity for the Black Hills region.",
      isAgent: true,
    },
    {
      title: "Zoning & Planning Monitor",
      file: "pages/zoning-monitor.html",
      tags: ["zoning", "planning", "permit", "variance", "county", "city", "rezone", "development", "box elder", "brigham city", "perry", "tremonton", "willard", "ordinance", "hearing", "agenda", "plat", "subdivision"],
      summary: "Scans county and city planning portals twice a week for new zoning changes, permits, and variance requests.",
      isAgent: true,
    },
    {
      title: "Contract & Lease Drafter",
      file: "pages/contract-drafter.html",
      tags: ["contract", "lease", "draft", "agreement", "purchase", "legal", "document", "closing", "contingency", "addendum", "terms", "buyer", "seller", "kw command", "compliance"],
      summary: "Generates draft contracts and lease agreements on demand from a simple intake form.",
      isAgent: true,
    },
    {
      title: "Customer Intake → CRM",
      file: "pages/crm-intake.html",
      tags: ["crm", "customer", "client", "intake", "kw command", "keller williams", "brivity", "constant contact", "newsletter", "contact", "lead", "buyer", "seller", "data entry", "form", "sync"],
      summary: "Web form that routes new client info automatically into KW Command, Brivity, and Constant Contact.",
      isAgent: true,
    },
    {
      title: "Development Site Evaluator",
      file: "pages/site-evaluator.html",
      tags: ["site", "evaluator", "development", "proforma", "feasibility", "parcel", "address", "apn", "zoning", "comps", "comparable", "noi", "cap rate", "irr", "returns", "go no-go", "industrial", "multi-family", "acquisition"],
      summary: "Enter a parcel address — get back zoning, comparable sales, proforma model, and a go/no-go recommendation.",
      isAgent: true,
    },
    {
      title: "Box Elder Land Prospecting",
      file: "pages/box-elder-prospects.html",
      tags: ["box elder", "prospecting", "land", "industrial", "multi-family", "parcels", "ownership", "brigham city", "perry", "tremonton", "willard", "i-15", "highway", "acres", "zoning", "m-1", "m-2", "r-3", "r-4", "leads", "outreach"],
      summary: "Weekly list of light industrial and multi-family land opportunities in Box Elder County with ownership data.",
      isAgent: true,
    },
    {
      title: "Mortgage Rates",
      file: "pages/market-report.html",
      tags: ["mortgage", "rate", "interest", "30 year", "15 year", "fed", "federal reserve", "fred", "financing", "loan"],
      summary: "30-year and 15-year fixed mortgage rates pulled weekly from the Federal Reserve (FRED). Current rates: 6.47% (30-yr) and 5.81% (15-yr), updated every Monday with the market report.",
      info: "The Market Report agent pulls rates from the FRED API (Federal Reserve Economic Data) every Monday at 6 AM — no login required. The current 30-yr fixed is <strong>6.47%</strong> (▼ 0.05% week-over-week) and 15-yr fixed is <strong>5.81%</strong>. These are included in the weekly email to Kevin.",
      isAgent: false,
    },
    {
      title: "KW Command",
      file: "pages/crm-intake.html",
      tags: ["kw", "keller williams", "command", "crm", "compliance", "paperwork", "payment", "record", "transaction"],
      summary: "KW Command is the required CRM for Keller Williams agents — handles client records, compliance, and payment processing.",
      info: "KW Command is Keller Williams' required CRM platform. It handles all client records, compliance documentation, and payment processing. The CRM Intake agent will automatically create records in KW Command when clients fill out a web form — eliminating manual data entry. A KW Command API key is needed to connect the agent (contact KW support).",
      isAgent: false,
    },
    {
      title: "Brivity",
      file: "pages/crm-intake.html",
      tags: ["brivity", "website", "market update", "drip", "campaign", "client", "email", "send"],
      summary: "Brivity hosts Kevin's website and supports drip campaigns and monthly market updates to clients.",
      info: "Brivity is the platform hosting Kevin's real estate website. It handles website drip campaigns and client-facing market updates. The CRM Intake agent can sync new contacts to Brivity automatically. Kevin currently uses Brivity to send market updates — the newsletter agent will draft content that gets sent through Brivity.",
      isAgent: false,
    },
    {
      title: "Constant Contact / Newsletter",
      file: "pages/market-report.html",
      tags: ["constant contact", "newsletter", "monthly", "email list", "client", "home value", "tips", "homeownership", "marketing"],
      summary: "Monthly newsletter platform — AI drafts it, Kevin reviews and hits send via KW Command or Brivity.",
      info: "Constant Contact manages Kevin's monthly newsletter list. Each month, the Market Report agent drafts a newsletter covering home values, mortgage rates, and homeownership tips. Kevin reviews the draft, then sends it via KW Command or Brivity. New contacts from the intake form are automatically added to the newsletter list.",
      isAgent: false,
    },
    {
      title: "Black Hills MLS",
      file: "pages/market-report.html",
      tags: ["mls", "black hills", "mount rushmore", "listing", "south dakota", "merge", "database", "credentials"],
      summary: "Kevin has Black Hills MLS and Mount Rushmore MLS access — the two boards are merging into one database later in 2026.",
      info: "Kevin has access to both the <strong>Black Hills MLS</strong> and <strong>Mount Rushmore MLS</strong>. The two boards are merging later in 2026. The Market Report agent currently uses Zillow public data and FRED — no MLS login required. Once the merge completes, we can integrate live MLS data for even more accurate reporting.",
      isAgent: false,
    },
    {
      title: "ZHVI — Zillow Home Value Index",
      file: "pages/market-report.html",
      tags: ["zhvi", "home value", "zillow", "index", "estimate", "price", "trend"],
      summary: "Zillow's estimated market value for typical homes in an area — used in the weekly market report for all 5 cities.",
      info: "ZHVI (Zillow Home Value Index) is Zillow's estimate of the typical home value in an area. It's available as a free public CSV — no API key needed. The market report uses ZHVI for all 5 cities: Rapid City, Spearfish, Sturgis, Hot Springs, and Box Elder. It's pulled fresh every Monday.",
      isAgent: false,
    },
    {
      title: "Rapid City Market",
      file: "pages/market-report.html",
      tags: ["rapid city", "south dakota", "market", "home value", "sale price", "inventory", "listings", "pending", "sold above list"],
      summary: "Primary market — gets a full spotlight card with home value, sale price, inventory, new listings, and % sold above asking.",
      info: "Rapid City is the primary market in the weekly report. It gets a full spotlight card with 5 metrics: <strong>Home Value (ZHVI)</strong>, <strong>Median Sale Price</strong>, <strong>Active Inventory</strong>, <strong>New Listings</strong>, and <strong>% Sold Above List Price</strong>. The other 4 cities (Spearfish, Sturgis, Hot Springs, Box Elder) get the 3 universal metrics in a regional table below.",
      isAgent: false,
    },
    {
      title: "Proforma Modeling",
      file: "pages/site-evaluator.html",
      tags: ["proforma", "model", "noi", "cap rate", "irr", "returns", "construction cost", "development", "feasibility", "investment"],
      summary: "The Site Evaluator builds a proforma with land cost, construction costs, projected NOI, cap rate, and IRR.",
      info: "The Development Site Evaluator generates a full proforma for any parcel address. It calculates: <strong>Land cost</strong> (from comparable sales) → <strong>Hard construction cost</strong> ($/sqft × buildable area) → <strong>Soft costs</strong> (15% of hard) → <strong>Total project cost</strong> → <strong>Projected NOI</strong> → <strong>Cap rate</strong> and <strong>IRR</strong>. Output is a PDF with a plain-English go/no-go recommendation.",
      isAgent: false,
    },
  ];

  // ── RESOLVE LINKS ─────────────────────────────────────────────────────
  // Build a correct relative URL from any page
  function resolveHref(item) {
    const parts = item.file.split('/');
    const filename = parts[parts.length - 1];
    if (item.file.startsWith('pages/')) {
      return inPages ? filename : 'pages/' + filename;
    }
    return inPages ? '../' + item.file : item.file;
  }

  // ── RELEVANCE SCORING ─────────────────────────────────────────────────
  function score(item, query) {
    const q = query.toLowerCase().trim();
    if (!q) return 0;
    const words = q.split(/\s+/);
    let s = 0;
    if (item.title.toLowerCase().includes(q)) s += 10;
    words.forEach(w => {
      if (item.title.toLowerCase().includes(w)) s += 4;
      if (item.summary.toLowerCase().includes(w)) s += 2;
      item.tags.forEach(t => { if (t.includes(w) || w.includes(t)) s += 1; });
    });
    return s;
  }

  function search(query) {
    return KB
      .map(item => ({ item, score: score(item, query) }))
      .filter(r => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 6)
      .map(r => r.item);
  }

  // ── INJECT STYLES ─────────────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = `
    #ka-btn {
      position: fixed; bottom: 24px; right: 24px; z-index: 9999;
      width: 52px; height: 52px; border-radius: 50%;
      background: linear-gradient(135deg, #8B5CF6, #3B82F6);
      border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      box-shadow: 0 4px 20px rgba(139,92,246,0.4);
      transition: transform .2s ease, box-shadow .2s ease;
    }
    #ka-btn:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(139,92,246,0.55); }
    #ka-btn svg { width: 22px; height: 22px; stroke: white; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

    #ka-panel {
      position: fixed; bottom: 88px; right: 24px; z-index: 9998;
      width: 370px; max-height: 540px;
      background: rgba(8,8,12,0.97);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 16px;
      box-shadow: 0 24px 60px rgba(0,0,0,0.7);
      backdrop-filter: blur(20px);
      display: none; flex-direction: column;
      overflow: hidden;
      font-family: 'Josefin Sans', sans-serif;
    }
    #ka-panel.open { display: flex; }

    #ka-header {
      padding: 16px 18px 12px;
      border-bottom: 1px solid rgba(255,255,255,0.07);
      display: flex; align-items: center; gap: 10px;
    }
    #ka-header-icon {
      width: 28px; height: 28px; border-radius: 8px;
      background: linear-gradient(135deg, #8B5CF6, #3B82F6);
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    #ka-header-icon svg { width: 14px; height: 14px; stroke: white; fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
    #ka-header-text { flex: 1; }
    #ka-header-title { font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(255,255,255,0.9); }
    #ka-header-sub   { font-size: 10px; color: rgba(255,255,255,0.3); margin-top: 1px; letter-spacing: 0.04em; }
    #ka-close { background: none; border: none; cursor: pointer; color: rgba(255,255,255,0.3); font-size: 18px; padding: 0; line-height: 1; transition: color .15s; }
    #ka-close:hover { color: rgba(255,255,255,0.7); }

    #ka-input-wrap {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.07);
      display: flex; align-items: center; gap: 8px;
    }
    #ka-input-wrap svg { width: 14px; height: 14px; stroke: rgba(255,255,255,0.25); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
    #ka-input {
      flex: 1; background: none; border: none; outline: none;
      font-family: 'Josefin Sans', sans-serif;
      font-size: 13px; color: rgba(255,255,255,0.85);
      letter-spacing: 0.02em;
    }
    #ka-input::placeholder { color: rgba(255,255,255,0.2); }

    #ka-body { flex: 1; overflow-y: auto; padding: 10px 0; }
    #ka-body::-webkit-scrollbar { width: 4px; }
    #ka-body::-webkit-scrollbar-track { background: transparent; }
    #ka-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 99px; }

    .ka-section-label {
      font-size: 9px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase;
      color: rgba(255,255,255,0.2); padding: 6px 16px 4px;
    }

    /* Agent results — click navigates to page */
    .ka-result {
      display: flex; align-items: flex-start; gap: 10px;
      padding: 10px 16px; cursor: pointer;
      transition: background .15s;
      text-decoration: none;
    }
    .ka-result:hover { background: rgba(255,255,255,0.05); }
    .ka-result-icon {
      width: 30px; height: 30px; border-radius: 8px;
      background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
      display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px;
    }
    .ka-result-icon svg { width: 13px; height: 13px; stroke: rgba(255,255,255,0.45); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .ka-result-name { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.85); margin-bottom: 2px; }
    .ka-result-desc { font-size: 11px; color: rgba(255,255,255,0.35); line-height: 1.5; }
    .ka-result-badge {
      font-size: 8px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
      padding: 2px 6px; border-radius: 4px; margin-left: 6px; vertical-align: middle;
      background: rgba(139,92,246,0.15); color: #A78BFA; border: 1px solid rgba(139,92,246,0.2);
    }
    .ka-result-arrow {
      margin-left: auto; padding-left: 8px; flex-shrink: 0; align-self: center;
      color: rgba(255,255,255,0.15); font-size: 16px;
    }

    /* Info popup card — for concept items */
    .ka-info-card {
      margin: 6px 12px 8px;
      padding: 14px 16px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 12px;
      cursor: pointer; transition: border-color .15s;
    }
    .ka-info-card:hover { border-color: rgba(255,255,255,0.2); }
    .ka-info-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .ka-info-card-icon {
      width: 26px; height: 26px; border-radius: 7px;
      background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
      display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    }
    .ka-info-card-icon svg { width: 12px; height: 12px; stroke: rgba(255,255,255,0.4); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .ka-info-card-title { font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.85); flex: 1; }
    .ka-info-card-body { font-size: 12px; color: rgba(255,255,255,0.55); line-height: 1.7; }
    .ka-info-card-link {
      display: inline-flex; align-items: center; gap: 4px; margin-top: 10px;
      font-size: 10px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
      color: #8B5CF6; text-decoration: none; transition: color .15s;
    }
    .ka-info-card-link:hover { color: #A78BFA; }

    /* Expanded info popup overlay inside panel */
    #ka-detail {
      position: absolute; inset: 0; z-index: 10;
      background: rgba(8,8,12,0.99);
      border-radius: 16px;
      display: none; flex-direction: column;
      overflow: hidden;
    }
    #ka-detail.open { display: flex; }
    #ka-detail-header {
      padding: 14px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.07);
      display: flex; align-items: center; gap: 10px;
    }
    #ka-detail-back {
      background: none; border: none; cursor: pointer;
      color: rgba(255,255,255,0.4); display: flex; align-items: center; gap: 4px;
      font-family: 'Josefin Sans', sans-serif; font-size: 11px; font-weight: 600;
      letter-spacing: 0.06em; text-transform: uppercase; padding: 0;
      transition: color .15s;
    }
    #ka-detail-back:hover { color: rgba(255,255,255,0.8); }
    #ka-detail-back svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    #ka-detail-title { font-size: 13px; font-weight: 700; color: rgba(255,255,255,0.9); }
    #ka-detail-body { flex: 1; overflow-y: auto; padding: 20px 18px; }
    #ka-detail-body::-webkit-scrollbar { width: 4px; }
    #ka-detail-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 99px; }
    #ka-detail-text {
      font-size: 13px; color: rgba(255,255,255,0.65); line-height: 1.8;
    }
    #ka-detail-text strong { color: rgba(255,255,255,0.9); }
    #ka-detail-goto {
      display: flex; align-items: center; justify-content: center; gap: 6px;
      margin-top: 20px; padding: 10px 16px;
      background: linear-gradient(135deg, rgba(139,92,246,0.15), rgba(59,130,246,0.15));
      border: 1px solid rgba(139,92,246,0.25); border-radius: 10px;
      font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
      color: #A78BFA; text-decoration: none; transition: background .15s;
    }
    #ka-detail-goto:hover { background: linear-gradient(135deg, rgba(139,92,246,0.25), rgba(59,130,246,0.25)); }

    .ka-empty { padding: 28px 20px; text-align: center; }
    .ka-empty-icon { font-size: 28px; margin-bottom: 8px; opacity: 0.3; }
    .ka-empty-text { font-size: 12px; color: rgba(255,255,255,0.25); line-height: 1.6; }

    .ka-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px 12px; }
    .ka-chip {
      font-size: 10px; font-weight: 600; letter-spacing: 0.04em;
      padding: 5px 10px; border-radius: 6px;
      background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1);
      color: rgba(255,255,255,0.45); cursor: pointer; transition: all .15s;
    }
    .ka-chip:hover { background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.8); border-color: rgba(255,255,255,0.2); }
  `;
  document.head.appendChild(style);

  // ── ICON PATHS ─────────────────────────────────────────────────────────
  const ICONS = {
    "Market":     `<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>`,
    "Zoning":     `<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>`,
    "Contract":   `<path d="M14 2H6a2 2 0 00-2 2v16h16V8z"/><polyline points="14 2 14 8 20 8"/>`,
    "Customer":   `<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>`,
    "Development":`<rect x="2" y="3" width="20" height="14" rx="2"/>`,
    "Box":        `<circle cx="12" cy="10" r="3"/><path d="M12 2a8 8 0 00-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 00-8-8z"/>`,
    "Mortgage":   `<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>`,
    "KW":         `<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/>`,
    "Brivity":    `<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>`,
    "Constant":   `<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>`,
    "Black":      `<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20"/>`,
    "ZHVI":       `<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>`,
    "Rapid":      `<path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>`,
    "Proforma":   `<rect x="2" y="3" width="20" height="14" rx="2"/>`,
    default:      `<circle cx="12" cy="12" r="10"/>`,
  };

  function iconFor(title) {
    const firstWord = title.split(" ")[0];
    return ICONS[firstWord] || ICONS.default;
  }

  // ── BUILD PANEL ────────────────────────────────────────────────────────
  const btn = document.createElement("button");
  btn.id    = "ka-btn";
  btn.setAttribute("aria-label", "Open search");
  btn.innerHTML = `<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`;

  const panel = document.createElement("div");
  panel.id    = "ka-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Dashboard search");
  panel.style.position = "relative";
  panel.innerHTML = `
    <div id="ka-header">
      <div id="ka-header-icon">
        <svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      </div>
      <div id="ka-header-text">
        <div id="ka-header-title">Search</div>
        <div id="ka-header-sub">Agents · Market data · Setup guides</div>
      </div>
      <button id="ka-close" aria-label="Close search">&times;</button>
    </div>
    <div id="ka-input-wrap">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input id="ka-input" type="text" placeholder="Search agents, market data, setup…" autocomplete="off" spellcheck="false"/>
    </div>
    <div id="ka-body"></div>
    <div id="ka-detail">
      <div id="ka-detail-header">
        <button id="ka-detail-back">
          <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
          Back
        </button>
        <div id="ka-detail-title"></div>
      </div>
      <div id="ka-detail-body">
        <div id="ka-detail-text"></div>
        <a id="ka-detail-goto" href="#">
          <svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          Go to related page
        </a>
      </div>
    </div>`;

  document.body.appendChild(btn);
  document.body.appendChild(panel);

  const body       = panel.querySelector("#ka-body");
  const input      = panel.querySelector("#ka-input");
  const detail     = panel.querySelector("#ka-detail");
  const detailTitle= panel.querySelector("#ka-detail-title");
  const detailText = panel.querySelector("#ka-detail-text");
  const detailGoto = panel.querySelector("#ka-detail-goto");
  const detailBack = panel.querySelector("#ka-detail-back");

  // ── SHOW DETAIL POPUP ─────────────────────────────────────────────────
  function showDetail(item) {
    detailTitle.textContent = item.title;
    detailText.innerHTML = item.info || item.summary;
    detailGoto.href = resolveHref(item);
    detailGoto.textContent = '';
    detailGoto.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg> Go to related page`;
    detail.classList.add("open");
  }

  detailBack.addEventListener("click", () => {
    detail.classList.remove("open");
  });

  // ── RENDER FUNCTIONS ──────────────────────────────────────────────────
  function agentResultHTML(item) {
    const href = resolveHref(item);
    const icon = iconFor(item.title);
    return `<a class="ka-result" href="${href}">
      <div class="ka-result-icon"><svg viewBox="0 0 24 24">${icon}</svg></div>
      <div style="flex:1">
        <div class="ka-result-name">${item.title}<span class="ka-result-badge">Agent</span></div>
        <div class="ka-result-desc">${item.summary}</div>
      </div>
      <div class="ka-result-arrow">›</div>
    </a>`;
  }

  function conceptResultHTML(item) {
    const icon = iconFor(item.title);
    return `<div class="ka-result ka-concept" data-title="${item.title}">
      <div class="ka-result-icon"><svg viewBox="0 0 24 24">${icon}</svg></div>
      <div style="flex:1">
        <div class="ka-result-name">${item.title}</div>
        <div class="ka-result-desc">${item.summary}</div>
      </div>
      <div class="ka-result-arrow">›</div>
    </div>`;
  }

  function resultHTML(item) {
    return item.isAgent ? agentResultHTML(item) : conceptResultHTML(item);
  }

  function bindConceptClicks() {
    body.querySelectorAll(".ka-concept").forEach(el => {
      el.addEventListener("click", () => {
        const title = el.dataset.title;
        const item = KB.find(k => k.title === title);
        if (item) showDetail(item);
      });
    });
  }

  function renderDefault() {
    body.innerHTML = `
      <div class="ka-section-label">Quick Topics</div>
      <div class="ka-chips">
        <span class="ka-chip">Mortgage rates</span>
        <span class="ka-chip">Box Elder</span>
        <span class="ka-chip">MLS access</span>
        <span class="ka-chip">KW Command</span>
        <span class="ka-chip">Newsletter</span>
        <span class="ka-chip">Proforma</span>
        <span class="ka-chip">Gmail setup</span>
        <span class="ka-chip">Zoning</span>
      </div>
      <div class="ka-section-label">All Agents</div>
      ${KB.filter(k => k.isAgent).map(resultHTML).join("")}`;
    body.querySelectorAll(".ka-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        input.value = chip.textContent;
        renderResults(chip.textContent);
      });
    });
    bindConceptClicks();
  }

  function renderResults(query) {
    const results = search(query);
    if (results.length === 0) {
      body.innerHTML = `<div class="ka-empty">
        <div class="ka-empty-icon">🔍</div>
        <div class="ka-empty-text">No results for "<strong>${query}</strong>"<br/>Try: mortgage rates, zoning, Box Elder, KW Command, newsletter, proforma</div>
      </div>`;
      return;
    }
    const agents   = results.filter(r => r.isAgent);
    const concepts = results.filter(r => !r.isAgent);
    let html = "";
    if (agents.length)   html += `<div class="ka-section-label">Agent Pages</div>${agents.map(resultHTML).join("")}`;
    if (concepts.length) html += `<div class="ka-section-label">Info — tap to expand</div>${concepts.map(resultHTML).join("")}`;
    body.innerHTML = html;
    bindConceptClicks();
  }

  // ── EVENTS ─────────────────────────────────────────────────────────────
  btn.addEventListener("click", () => {
    const isOpen = panel.classList.contains("open");
    panel.classList.toggle("open");
    if (!isOpen) {
      detail.classList.remove("open");
      renderDefault();
      setTimeout(() => input.focus(), 50);
    }
  });

  panel.querySelector("#ka-close").addEventListener("click", () => {
    panel.classList.remove("open");
    input.value = "";
  });

  let debounceTimer;
  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    detail.classList.remove("open");
    debounceTimer = setTimeout(() => {
      const q = input.value.trim();
      if (!q) renderDefault();
      else renderResults(q);
    }, 180);
  });

  input.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      if (detail.classList.contains("open")) detail.classList.remove("open");
      else { panel.classList.remove("open"); input.value = ""; }
    }
  });

  document.addEventListener("click", e => {
    if (!panel.contains(e.target) && e.target !== btn) {
      panel.classList.remove("open");
    }
  });

})();
