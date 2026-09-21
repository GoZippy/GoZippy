# Zippy profile: operating notes

This is a local, reviewable candidate for the `GoZippy/GoZippy` profile repository. Nothing is published or scheduled. The previous profile design is preserved in `archive/20260920-brand-v1/` locally and is excluded from the publication package.

## What changes automatically

The collector can refresh an aggregate calendar from GitHub. The renderer regenerates the contribution card and the dated summary from that sanitized file. Project descriptions, WIP status, tools and selected PRs remain curated. They do not change simply because an agent committed something in a private repository.

From the profile directory, with Python and the existing authenticated GitHub CLI:

```powershell
python scripts/refresh_activity.py --fetch --login GoZippy --output data/activity.json
python scripts/render_profile.py
```

Run the renderer only after a successful refresh, or intentionally retain the previous dated snapshot. The fetch fails without replacing the old snapshot if authentication, identity, date coverage, counts or the response are invalid. It never requests private repository names, branch names or commit messages. Dates/counts and a scope statement are the entire display input.

The SVG renderer requires `fonttools` (version in `requirements-render.txt`); fonts and the license are under `assets/fonts/`. The fetcher and its tests require only Python's standard library plus GitHub CLI when using its existing login. An explicit token environment variable can be used instead; never put credentials in a command argument, file or public repository.

For local preview generation, the source workspace also contains `scripts/render_preview.py` and `build_preview.py`. The first uses GitHub's Markdown API as a rendering service; it does not publish. The preview approximates GitHub's surrounding styling. No JavaScript app, custom tabs or WebGL controls are portrayed as native README features.

## Periodic refresh candidate

`automation/refresh-profile.yml` is deliberately outside `.github/workflows`. After separate installation and owner credential setup, it offers daily/manual refresh and uploads a sanitized JSON artifact for review. It has no write permission, commit step, PR creation or publication step. **It does not automatically update the live README or graphic.** Promotion and publication can be added as a separately authorized step after the first profile is accepted.

The custom snapshot represents the authorized viewer's contribution calendar. These are contributions, not commits or hours worked. Do not compute a public/private split from `restrictedContributionsCount`. GitHub's own private-contribution visibility preference is unchanged.

## Keep it compact and truthful

- Keep the three main drawers: compute, worlds and agents. Add depth inside the drawers rather than another long feed.
- Mark concepts and WIP clearly. Replace a concept with actual demo footage only when that footage is ready to share.
- The official Z sphere stays intact. Project colors can vary; preserve Open Sans and the brand guidance.
- Decorative SVG motion ends after at most 14 seconds. Reduced-motion visitors receive a static hero; all SVGs also disable animation under that preference.
- There are no third-party stats-image services, visitor trackers, runtime credential requests or embedded scripts in the profile images.
- Refresh public PR state before editing its label. A fork is not the same as an accepted upstream contribution.
- Publicly unresolved project URLs were removed. User-named projects remain high-level WIP entries, with no private repository links.

## Publication package

Only copy the reviewed README, referenced assets (including `assets/proof.svg` and `assets/collab.svg`), curated data, templates, scripts, render requirements and tests from the prepared candidate package. The inactive automation file may be retained as documentation. Do not publish the whole social-workspace folder, raw session history, archive, or private run folder.

Before publication, render on GitHub and check the image proxy's animation behavior on the actual profile. Local animation checks and Markdown sanitization checks do not establish public image-proxy playback. If needed, use `hero-static.svg`; no information is lost.
