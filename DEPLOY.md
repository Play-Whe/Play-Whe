# Deploying Play Whe to play-whe.com

Everything lives in one place now: GitHub hosts the site (GitHub
Pages), runs the scraper on a schedule (GitHub Actions), and the two
talk to each other through this same repo — no separate hosting
account needed.

## 1. Push this repo to GitHub

1. Create a new **public** repository on GitHub (e.g. `play-whe`).
   Public is required — GitHub Pages needs a paid plan for private
   repos.
2. Push all these files to it, **including the `.github/` folder**
   (GitHub won't run Actions unless that folder is in the repo) and
   the `CNAME` file (already set to `play-whe.com`).

## 2. Turn on GitHub Pages

1. In the repo: **Settings → Pages**.
2. Under "Build and deployment", set **Source** to `Deploy from a
   branch`.
3. Branch: `main`, folder: `/ (root)`. Save.
4. GitHub builds and gives you a live URL at
   `https://<your-username>.github.io/play-whe/` within a minute or
   two — check it loads before moving to the domain step.

## 3. Turn on the scraper (GitHub Actions)

No extra setup — the workflow at
`.github/workflows/update-results.yml` is already in the repo, and
GitHub enables Actions automatically for public repos. It will:

- Run a few minutes after each of the 4 daily draws (10:30 AM, 1 PM,
  4 PM, 6:30 PM AST, Mon–Sat), with a couple of retries each time in
  case results post a little late
- Scrape the results page and update `results.json`
- Commit that file back to the repo

Every commit — including the scraper's automated ones — makes GitHub
Pages rebuild automatically, so a new draw shows up on the live site
within a couple of minutes of the scraper catching it. Nothing manual
needed once this is on.

**Before relying on it:** go to the repo's **Actions** tab and run the
workflow manually once (`Run workflow` button) to confirm it actually
scrapes successfully. The scraper's selectors were written without
live testing (see the warning comments in `playwhe_scraper.py`) — if
the target site's HTML has changed, you'll need to adjust
`parse_results()` against the real page's HTML before trusting it
unattended.

## 4. Connect play-whe.com (bought on GoDaddy)

1. In the repo: **Settings → Pages → Custom domain** → enter
   `play-whe.com` → Save. (This double-checks the `CNAME` file
   already in the repo matches.)
2. Log into GoDaddy → your domain → **DNS Management**, and add
   **four A records**, all with host `@`, pointing to GitHub Pages'
   servers:

   ```
   185.199.108.153
   185.199.109.153
   185.199.110.153
   185.199.111.153
   ```

3. Optional but recommended — also add a **CNAME record** with host
   `www` pointing to `<your-username>.github.io`, so
   `www.play-whe.com` works too and GitHub can redirect one to the
   other.
4. Wait for DNS to propagate (usually 15 minutes to a few hours,
   occasionally up to 24h).
5. Back in **Settings → Pages**, once GitHub confirms the DNS is
   correct, check **Enforce HTTPS** — GitHub auto-provisions a free
   certificate (Let's Encrypt) once that's available.

That's the whole path to `https://play-whe.com` being live,
self-updating, and free — GitHub Pages and Actions both comfortably
cover a site and scraper this size at no cost.

## What still needs real-world testing

- The scraper's HTML selectors (flagged above) — this is the one
  piece that hasn't touched the live internet yet.
- NLCB's own terms of use for the underlying data — this bootstraps
  you to launch, but revisit getting official data access once the
  site has real traffic, as discussed earlier.
