# Hemicycle Brief

Your own EU news website. Every morning a bot reads left-leaning, right-leaning and straight-news outlets, keeps the EU stories, and shows each story with both sides' coverage next to each other. It runs for free on GitHub: no server, no Claude account.

```
site/        the website (index.html, assets/, data/)
bot/         the morning bot (update.py) and the outlet list (feeds.json)
.github/     the daily schedule that runs the bot and publishes the site
```

## Two modes

- **Headlines mode (free, default).** The site shows stories that both sides covered, with each outlet's headline and link, plus a list of stories only one side covered.
- **Written mode (optional, a few cents a day).** Add a Claude API key and the bot also writes a neutral summary, why it matters, how each side frames it, and where they differ, like the first edition already on the site.

## Put it online (about 10 minutes)

1. **Make a GitHub account** at github.com (free).
2. **Create a repository**: the **+** menu → *New repository* → name it `hemicycle-brief` → **Public** → *Create repository*.
3. **Upload the files**: on the new repository page click *uploading an existing file*, drag in everything from this folder, then *Commit changes*.
   - Check that the `.github` folder arrived. Your computer may hide it because the name starts with a dot. If it is missing: *Add file* → *Create new file*, type `.github/workflows/daily.yml` as the name, paste in the contents of that file from this folder, and commit.
4. **Turn on the website**: *Settings* → *Pages* → under *Build and deployment*, set *Source* to **GitHub Actions**.
5. **Run the bot once**: *Actions* tab → *Daily brief* → *Run workflow*. After a minute or two your site is live at
   `https://YOUR-GITHUB-NAME.github.io/hemicycle-brief/`

From then on it updates itself every morning at 06:33 Madrid time (07:33 in summer). GitHub sometimes starts scheduled runs a few minutes late.

## Optional: written summaries with Claude

1. Get an API key at console.anthropic.com (the Claude API is billed separately from a Claude.ai subscription).
2. In your repository: *Settings* → *Secrets and variables* → *Actions* → *New repository secret*. Name it `ANTHROPIC_API_KEY` and paste the key.
3. The next run uses written mode. It uses Claude Sonnet 5.5 by default, which costs roughly €1–2 a month at one edition a day. For a cheaper run, add a repository **variable** (same page, *Variables* tab) named `CLAUDE_MODEL` with the value `claude-haiku-5-5`.

If the API call fails for any reason, the bot falls back to headlines mode for that day.

## Change the outlets

Edit `bot/feeds.json`. Each outlet has a `side` (`left`, `right` or `centre`), a `lean` label shown on the site, and a feed `url`. Feed addresses sometimes change: the bottom of the site lists any feed the bot couldn't reach that morning, so you know which one to fix or remove.

## Use your own domain

*Settings* → *Pages* → *Custom domain*, then follow GitHub's instructions for your domain provider.

## Preview or test on your computer

```
python3 -m http.server -d site 8000        # then open http://localhost:8000
pip install -r bot/requirements.txt
python3 bot/update.py --no-ai              # writes today's edition into site/data
```

Opening `site/index.html` directly by double-clicking won't load the editions; use the preview command above.

## Notes

- Summaries and framing notes are written fresh; the site only shows outlets' headlines and links, never their article text.
- Fonts load from Google Fonts. If you want to avoid that (some EU sites do for privacy reasons), delete the three `fonts.googleapis.com` / `fonts.gstatic.com` lines in `site/index.html`; the page falls back to system fonts.
- Leanings are approximate, based on widely used media-bias ratings. Adjust them in `feeds.json` if you disagree.
