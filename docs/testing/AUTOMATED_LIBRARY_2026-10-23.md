# Scheduled template authoring, archive and trial acceptance

> 2026-10-26 update: qualified automatic publication is now enabled after the new end-to-end acceptance. See [current rollout and share-cover evidence](AUTO_PUBLICATION_2026-10-26.md). The held rollout described below records the original 2026-10-23 state.

This deployment separates discovery, downloaded candidates, compiled drafts, actual visual review and published templates. Only final published keys count as additions. Public website text and model responses are data, never executable code.

## Runtime paths and limits

- Mainland MiniMax subscription credentials: `/etc/gensticker-minimax.env`, root-owned 0600, loaded only by the ingestion service. No ordinary paid-key fallback. Native vision uses the configured official mainland host and M-series multimodal model. Skill files are bundled under `features/authoring/` and their SHA256 is attached to review evidence.
- The scheduler runs at 00/06/12/18 Beijing time with at most 20 minutes jitter. Default target is five new templates, constrained to 3–10; a run publishing fewer than three exits with attention. Quota/source/quality failures do not trigger filler templates or weaker gates. Daily model-call and source-download limits persist in SQLite.
- Candidate sources include configured public pages, MiniMax search results, Weshine public markup and immutable ChineseBQB revisions across six rotating categories. The operator has explicitly authorized attributed public sources with unverified per-image rights. Record actual source and image URLs; do not invent authors or treat attribution as verified licensing. Authenticated/private/blocked pages are not bypassed.
- Public HTTP fetches are bounded and pin a publicly routed DNS result. Redirects are revalidated, credentials are never forwarded, and private network addresses are rejected.
- Automatic face admission additionally requires independently measured person-face proposal coverage and all required feature points inside the removal mask. Unknown/occluded/cartoon geometry remains pending, regardless of model score. Sources retain at most 40 frames, 8 MP normalized decoded pixels and an eight-second loop. The compiler performs existing face/caption replacement in the original scene and timeline, not appended panels. Local OCR and pinned YuNet measurements assist the vision model. The ONNX model SHA256 is `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`; see the bundled third-party license.
- Verification renders real avatar replacement, blank captions and changed/multiline captions for every frame. Protected source pixels, frame counts and timing are checked locally; a native MiniMax review and the separate Token Plan image-understanding endpoint check actual rendered boards. Rejected samples remain pending. A numerical or model pass alone does not establish equivalence to the prior human/Codex-reviewed library: the initial same-source comparison must also be inspected independently.
- Compiled work is isolated from live assets. Publication and batch membership commit atomically; public materialization checks space and file counts. Temporary/evidence/source caches have retention and byte caps. The catalog has a transactionally enforced hard ceiling of 8000 published templates, also on archive restoration.

## Monthly GitHub archive

The target is **MIKL2077/GenSticker**, orphan branch **template-archive**. It is separate from application source history. The deployment SSH key is scoped to this repository; no personal HTTPS token is installed on the server. Because this is the existing project repository, archive visibility follows that repository's visibility. Only public-source templates/artwork may enter it; user-provided templates, creator material, customer photos, private inputs and generated customer results are excluded.

`gensticker-archive.timer` runs on the first of each month at 04:00 Beijing time with jitter. It records an inventory and selects already-withdrawn public templates, then templates older than 90 days without recent positive usage. Favorites and retained job/results references are protected. The 294 bundled runtime templates remain the local baseline; automatic retirement currently targets declarative public-source templates. Preserve at least 1000 published templates when retiring cold active entries. The shared public catalog still never exceeds 8000.

Every archive preserves the stable UUID/key, current and historical versions, source attribution, recipe fingerprints and content-addressed artwork. Upload first, fetch all objects again through a new Git workspace, verify hashes, recheck references/version under the storage lock, then mark archived and evict only unshared local artwork. Temporary sparse bare Git workspaces are removed afterward. A rejected push/readback never authorizes eviction. Startup seed restoration skips archived keys.

The conservative archive budget is 3 GiB; reaching it pauses further archival and reports attention rather than deleting history. Monthly progress is persisted after each item. A bounded run reports remaining work; rerun to resume. Git history and existing deployment/backup copies are separate from the live artwork space and are not silently deleted.

Operator commands, via the installed root-only wrapper:

```sh
sudo gensticker-template-admin list
sudo gensticker-template-admin report
sudo gensticker-template-admin monthly
sudo gensticker-template-admin restore --key TEMPLATE_KEY
sudo gensticker-template-admin restore --key TEMPLATE_KEY --version VERSION
```

Restoration verifies the pinned remote commit, manifest and every image, reserves local capacity, and restores the original state/UUID/version. A template that was withdrawn before archival restores as withdrawn, not silently republished. An originally published cold template restores as published if capacity allows. Operators must not bypass report/quality blocks to publish unsafe material.

## Daily/batch trial card

`GET /templates/trial` selects the best quality score from the most recent successful publication cohort, rotates daily if no newer cohort arrives, and falls back to clearly labelled daily curated templates before the first new batch. `POST /templates/trial/use` records an account/visitor-bound use. Responses are private to the request identity (`no-store`, `Vary` headers). Frontend checks on page show and once per visible minute, stops polling on hide, hides immediately after a successful accepted generation, and keeps usage locally plus server-side. Switching accounts does not leak another account's use history. Another newly featured key can appear normally.

## Log management

- Global journal: 1 GiB, 14 days, 10 GiB free-space reserve; compressed.
- Nginx and rsyslog text logs: daily or over 50 MiB at hourly checks, fourteen compressed rotations. Thus the size trigger is checked hourly, not an instantaneous hard cap on each active file.
- Docker daemon default: `local`, 20 MiB × three files, compression. No running containers existed at deployment. The unrelated stopped legacy container was not recreated and retains its old driver; it is not GenSticker's runtime.
- Model error bodies, authorization headers, API keys and user photos are excluded from journals. Ingestion and archive attention statuses feed the existing private monitor; this is not an external notification subscription.

## Acceptance evidence

Local/native/remote evidence is recorded in `docs/testing/evidence/automated-library-20261023.json` once final acceptance completes. Large visual comparisons and native screenshots stay in ignored `artifacts/automated-library-20261023/`.

The actual GitHub round trip uses one already-withdrawn public template and checks exact SQLite rows, all versions and all artwork before re-archiving it. No active template is used as a destructive test fixture. Native WeChat acceptance retrieves the real trial, generates with the licensed cat fixture, confirms immediate hide and confirms hidden state after page reload.

The MiniMax comparison uses the same original bytes, avatar and changed captions as the last accepted version, including an animated timeline and multi-line captions. Record unsuccessful cases as rejected, not as equivalent. An initial quality failure keeps unattended publishing disabled until the acceptance gate is deliberately satisfied.

## Current acceptance disposition

The rollout is **partial**. Log management, the archive/restore path, the 8000-template ceiling and daily/account-bound trial behavior passed acceptance. The October archive completed 59 eligible templates, freed 13,137,006 live artwork bytes and retained all 944 published templates. The initial separate archive fixture also remains recoverable.

MiniMax authoring is implemented and real-source pilots were run, but unattended publication has **not** met the requested quality/yield acceptance. Two real new meme examples passed independent Codex inspection. The same-source comparison accepted the ordinary portrait example; occlusion, multiline and animated cases remained rejected. A model score of 96 incorrectly approved retained original eyes/mouth, and the Token Plan VLM repeated review was not fully consistent either. The final publication boundary therefore requires locally measured face coverage plus both rendered-image reviews; scores alone cannot admit a face template. A separate related-photo false positive led to restricting generic web pages to their declared main meme artwork, rather than recommendation thumbnails.

`GENSTICKER_MINIMAX_ENABLED=0` is deliberately retained on the server. Six-hour metadata collection continues without model calls and reports `held-for-quality`; images are not automatically published. The target of 3–10 qualified new public templates per run is **not achieved/accepted**, and this report does not label drafts or model-only approvals as new public templates. The final user acceptance must distinguish implemented code from this remaining rollout blocker.

The image fixtures and rendered comparisons are in the ignored local `artifacts/automated-library-20261023/` directory. Actual generated user photographs are never sent to MiniMax or placed in GitHub archives.

The quality hold follows the user's explicit equivalence requirement and [meme-to-template SKILL.md](../../skills/meme-to-template/SKILL.md): “Do not weaken gates to inflate counts”. It is based on actual failed rendered comparisons, not a hypothetical approval policy.
