(function () {

  // ------------------------------
  // DEFAULT CONFIG FOR YOUR PROJECT
  // ------------------------------
  const DEFAULT_CONFIG = {
    //title: 'DLS Information Centre',
    pages: [
      { label: 'Rig Overview', href: '/rig-overview' },
      { label: 'Getting Started', href: '/getting-started' },
      { label: 'PDF Chart Generation', href: '/pdf-chart-generation' },
      { label: 'Historical Trend', href: '/historical-trend' }
    ]
  };

  // ------------------------------
  // Inject Styles Once
  // ------------------------------
  function ensureStyles() {
    if (document.getElementById('shared-nav-styles')) return;

    const style = document.createElement('style');
    style.id = 'shared-nav-styles';
    style.textContent = `
      .app-navbar {
        background: linear-gradient(180deg, #181818 0%, #141414 100%);
        border: 1px solid #303030;
        border-radius: 10px;
        color: #f5f5f5;

        display: flex;
        align-items: center;
        justify-content: space-between;

        height: 50px !important;
        min-height: 50px !important;
        max-height: 50px !important;

        padding: 0 14px !important;
        box-sizing: border-box !important;

        gap: 12px;
        box-shadow: 0 6px 14px rgba(0,0,0,0.35);
        position: sticky;
        top: 0;
        z-index: 50;
      }


      .app-navbar * {
        box-sizing: border-box;
        line-height: 1 !important;
      }


      .nav-left, .nav-right {
        display: flex;
        align-items: center;
        gap: 14px;
      }

      .nav-icon-btn {
        width: 38px;
        height: 34px;
        border-radius: 8px;
        border: 1px solid #3a3a3a;
        background: #1d1d1d;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
      }

      .nav-icon-btn span,
      .nav-icon-btn span::before,
      .nav-icon-btn span::after {
        display: block;
        width: 18px;
        height: 2px;
        background: #e8e8e8;
        border-radius: 999px;
        position: relative;
      }

      .nav-icon-btn span::before {
        content: '';
        position: absolute;
        top: -6px;
        left: 0;
      }

      .nav-icon-btn span::after {
        content: '';
        position: absolute;
        top: 6px;
        left: 0;
      }

      .nav-menu {
        position: absolute;
        top: calc(100% + 8px);
        left: 0;
        background: #1a1a1a;
        border: 1px solid #2e2e2e;
        border-radius: 10px;
        padding: 8px;
        min-width: 180px;
        display: none;
        box-shadow: 0 14px 28px rgba(0,0,0,0.45);
      }

      .nav-menu.open { display: block; }

      .nav-menu a {
        display: block;
        padding: 10px 10px;
        border-radius: 8px;
        color: #f5f5f5;
        text-decoration: none;

        font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        font-size: 14px;
        font-weight: 500;
        line-height: 1.2;
      }

      .nav-title {
        font-size: 18px;
        font-weight: 600;
      }

      .nav-clock {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        line-height: 1.1;
      }

      .nav-time {
        font-size: 16px;
        font-weight: 600;
      }

      .nav-date {
        font-size: 12px;
        color: #cfcfcf;
      }

      .nav-logo-wrapper {
        display: flex;
        align-items: center;
      }

      .nav-logo {
        width: 32px;
        height: 32px;
        border-radius: 6px;
        cursor: pointer;
        transition: opacity 0.2s;
      }

      .nav-logo:hover { opacity: 0.8; }
    `;
    document.head.appendChild(style);
  }

  // ------------------------------
  // Build Dropdown
  // ------------------------------
  function buildMenuItems(menu, pages) {
    menu.innerHTML = "";
    pages.forEach(page => {
      const a = document.createElement('a');
      a.href = page.href;
      a.textContent = page.label;
      menu.appendChild(a);
    });
  }

  // ------------------------------
  // Build Navbar
  // ------------------------------
  function initNavigationBar(config = {}) {
    ensureStyles();

    const merged = { ...DEFAULT_CONFIG, ...config };

    const header = document.createElement('header');
    header.className = "app-navbar";

    // LEFT SECTION
    const left = document.createElement('div');
    left.className = "nav-left";

    const navWrapper = document.createElement('div');
    navWrapper.style.position = "relative";

    const iconBtn = document.createElement('button');
    iconBtn.className = "nav-icon-btn";
    iconBtn.innerHTML = "<span></span>";

    const navMenu = document.createElement('div');
    navMenu.className = "nav-menu";

    buildMenuItems(navMenu, merged.pages);

    navWrapper.appendChild(iconBtn);
    navWrapper.appendChild(navMenu);

    left.appendChild(navWrapper);

    const title = document.createElement('div');
    title.className = "nav-title";
    title.textContent = merged.title;
    left.appendChild(title);

    // RIGHT SECTION
    const right = document.createElement('div');
    right.className = "nav-right";

    // clock
    const clock = document.createElement('div');
    clock.className = "nav-clock";

    const timeEl = document.createElement('div');
    timeEl.className = "nav-time";

    const dateEl = document.createElement('div');
    dateEl.className = "nav-date";

    clock.appendChild(timeEl);
    clock.appendChild(dateEl);

    // logo
    const logoWrapper = document.createElement('div');
    logoWrapper.className = "nav-logo-wrapper";

    const logoImg = document.createElement('img');
    logoImg.src = "../Style/Green Oliver V.png";
    logoImg.alt = "Oliver Valves Logo";
    logoImg.className = "nav-logo";

    logoImg.addEventListener("click", () => {
      window.location.href = "../Rig-Overview/Rig-Overview.html";
    });

    logoWrapper.appendChild(logoImg);

    right.appendChild(clock);
    right.appendChild(logoWrapper);

    header.appendChild(left);
    header.appendChild(right);

    // clock tick
    function updateClock() {
      const now = new Date();
      timeEl.textContent = now.toLocaleTimeString('en-GB', { hour12: false });
      dateEl.textContent = now.toLocaleDateString('en-GB');
    }
    updateClock();
    setInterval(updateClock, 1000);

    // menu toggle
    iconBtn.addEventListener('click', e => {
      e.stopPropagation();
      navMenu.classList.toggle('open');
    });

    document.addEventListener('click', () => {
      navMenu.classList.remove('open');
    });

    // inject into page
    document.body.prepend(header);
  }

  window.initNavigationBar = initNavigationBar;

})();
