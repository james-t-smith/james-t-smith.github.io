/**
 * site-chrome.js — populates the shared header on EVERY page (brand
 * name, Resume/Portfolio nav links) from site/data/title.json.
 *
 * Fixes two bugs from earlier versions of this site: the brand name
 * in the header was hardcoded as literal text ("Your Name") and never
 * actually replaced with data/title.yaml's real name, and the Resume
 * nav link pointed at "resume.pdf" even when no such file had been
 * copied into site/ — scripts/build.py now copies compiled PDFs into
 * site/ on every run (see sync_pdfs_to_site()), and this script wires
 * the links up to wherever title.yaml says they should point.
 *
 * Included on both index.html and project.html so the toolbar is
 * always consistent, independent of whichever page-specific script
 * (load-projects.js / render-project.js) also runs on that page.
 */
(function () {
  async function fetchJSON(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error('Failed to fetch ' + path);
    return res.json();
  }

  async function main() {
    let title;
    try {
      title = await fetchJSON('data/title.json');
    } catch (err) {
      console.error('site-chrome: could not load data/title.json', err);
      return;
    }

    const brandEl = document.querySelector('[data-brand]');
    if (brandEl && title.name) brandEl.textContent = title.name;

    const resumeLink = document.querySelector('[data-nav-resume]');
    if (resumeLink) {
      if (title.resume_pdf) {
        resumeLink.href = title.resume_pdf;
        resumeLink.hidden = false;
      } else {
        resumeLink.hidden = true;
      }
    }

    const portfolioLink = document.querySelector('[data-nav-portfolio]');
    if (portfolioLink) {
      if (title.portfolio_pdf) {
        portfolioLink.href = title.portfolio_pdf;
        portfolioLink.hidden = false;
      } else {
        portfolioLink.hidden = true;
      }
    }
  }

  main();
})();
